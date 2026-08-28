from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sancho.mcp.models import MCPContext, MCPPolicy
from sancho.mcp.tooling import (
    _LEGACY_MCP_PROTOCOL_VERSIONS,
    _META_PROTOCOL_VERSION_KEY,
    _MODERN_MCP_PROTOCOL_VERSIONS,
    MCPHeaderMismatch,
    MCPUnsupportedProtocolVersion,
    ProtocolEra,
    _build_context,
    _handle_method,
    _tools_payload,
    jsonrpc_error,
)


class _EnvelopeError(ValueError):
    """Transport-boundary rejection carrying a JSON-RPC error code."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _read_stdio_message() -> dict[str, Any] | None:
    """Read one JSON-RPC message from stdin per the MCP stdio transport spec.

    Framing is newline-delimited JSON: each message is a single line of UTF-8
    JSON terminated by ``\\n``, with no embedded newlines. This is what Claude
    Desktop, Codex, Cursor, VS Code, and every other MCP client send.
    """
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        stripped = line.strip()
        if not stripped:
            # Skip blank lines between messages.
            continue
        try:
            message = json.loads(stripped.decode("utf-8"))
        except json.JSONDecodeError:
            # Malformed line; skip and try the next one.
            continue
        if isinstance(message, dict):
            return message
        # Non-object JSON (array/scalar) is never a valid JSON-RPC message;
        # skip it rather than crash the read loop downstream.
        continue


def _write_stdio_message(payload: dict[str, Any]) -> None:
    """Write one JSON-RPC message to stdout as newline-delimited JSON.

    Per the MCP stdio transport spec: one UTF-8 JSON object per line,
    ``\\n``-terminated, no embedded newlines. ``json.dumps`` does not emit
    newlines inside the serialized output, so the spec guarantee holds.
    """
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def serve_stdio(
    workspace_root: Path,
    *,
    policy: MCPPolicy | None = None,
    quick_mode: bool = False,
    quick_profile: str | None = None,
    quick_targets: list[str] | tuple[str, ...] | None = None,
    quick_modules: list[str] | tuple[str, ...] | None = None,
) -> None:
    ctx = _build_context(
        workspace_root=workspace_root,
        policy=policy,
        quick_mode=quick_mode,
        quick_profile=quick_profile,
        quick_targets=quick_targets,
        quick_modules=quick_modules,
    )

    stdio_era = None
    while True:
        message = _read_stdio_message()
        if message is None:
            break
        method = message.get("method")
        message_id = message.get("id")
        if not isinstance(method, str) or not method:
            continue

        if method.startswith("notifications/"):
            continue

        try:
            params = message["params"] if "params" in message else {}
            request_era = "legacy" if method == "initialize" else stdio_era
            result = _handle_method(
                ctx,
                method=method,
                params=params,
                protocol_era=request_era,
            )
            # A successful legacy initialize is a real handshake and always
            # pins legacy serialization for the whole process — even after a
            # modern server/discover probe. A server/discover only latches
            # modern when no handshake has happened; mid-legacy-session it is
            # served as modern per-request without unpinning the legacy client.
            if method == "initialize":
                stdio_era = "legacy"
            elif method == "server/discover" and stdio_era is None:
                stdio_era = "modern"
            if message_id is not None:
                _write_stdio_message({"jsonrpc": "2.0", "id": message_id, "result": result})
        except Exception as exc:
            if message_id is not None:
                _write_stdio_message(
                    {"jsonrpc": "2.0", "id": message_id, "error": jsonrpc_error(exc)}
                )


class _HttpHandler(BaseHTTPRequestHandler):
    ctx: MCPContext

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise _EnvelopeError(-32600, "Content-Length header must be an integer") from None
        # Defensive upper bound on request body size. When policy.max_request_bytes
        # is 0 (default, local/stdio/non-hosted) we still apply a generous 10 MB
        # cap so a malformed or hostile client can't exhaust memory reading an
        # unbounded body.
        max_req = self.ctx.policy.max_request_bytes or (10 * 1024 * 1024)
        if length < 0 or length > max_req:
            raise _EnvelopeError(-32600, f"Request body exceeds {max_req}-byte limit")
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise _EnvelopeError(-32700, "Request body is not valid JSON") from None
        if not isinstance(payload, dict):
            raise _EnvelopeError(
                -32600,
                "Request payload must be a single JSON-RPC object; batching is not supported",
            )
        return payload

    def _setup_request_state(self, parsed_path: Any) -> None:
        """Stash per-request runtime state into thread-local storage."""
        from sancho.runtime import request_state

        _ = parsed_path
        request_state.set_stateless(self.ctx.policy.stateless)

    def _teardown_request_state(self) -> None:
        from sancho.runtime import request_state

        request_state.clear()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"ok": True})
            return
        if self.path == "/tools":
            self._write_json(200, _tools_payload(self.ctx))
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self._setup_request_state(parsed)
        try:
            self._do_POST_inner(parsed)
        finally:
            self._teardown_request_state()

    def _check_mcp_headers(self, method: str, params: Any) -> ProtocolEra | None:
        """Validate routing headers and derive the era they imply.

        Handshake-era streamable-HTTP clients MUST send
        ``MCP-Protocol-Version: <negotiated legacy version>`` on every
        post-initialize request (required since 2025-06-18) and never send
        ``_meta``, so a legacy header value is a routing signal, not a
        mismatch. Returns the era the header selects, or ``None`` when the
        header is absent and the body decides.
        """
        header_method = self.headers.get("Mcp-Method")
        if header_method and header_method != method:
            raise MCPHeaderMismatch(
                f"Mcp-Method header '{header_method}' does not match body method '{method}'"
            )
        header_name = self.headers.get("Mcp-Name")
        if header_name and method == "tools/call":
            body_name = params.get("name") if isinstance(params, dict) else None
            if header_name != body_name:
                raise MCPHeaderMismatch(
                    f"Mcp-Name header '{header_name}' does not match params.name '{body_name}'"
                )
        meta = params.get("_meta") if isinstance(params, dict) else None
        body_version = (
            meta.get(_META_PROTOCOL_VERSION_KEY) if isinstance(meta, dict) else None
        )
        header_version = self.headers.get("MCP-Protocol-Version")
        if method == "server/discover":
            if header_version not in {None, *_MODERN_MCP_PROTOCOL_VERSIONS}:
                raise MCPHeaderMismatch(
                    f"MCP-Protocol-Version header '{header_version}' is not valid for discovery"
                )
            return "modern"
        if header_version is None:
            if body_version in _MODERN_MCP_PROTOCOL_VERSIONS:
                raise MCPHeaderMismatch(
                    "modern HTTP requests require the MCP-Protocol-Version header"
                )
            return None
        if header_version in _MODERN_MCP_PROTOCOL_VERSIONS:
            if body_version != header_version:
                raise MCPHeaderMismatch(
                    f"MCP-Protocol-Version header '{header_version}' does not match "
                    f"params._meta protocol version '{body_version}'"
                )
            return "modern"
        if header_version in _LEGACY_MCP_PROTOCOL_VERSIONS:
            if body_version is not None:
                raise MCPHeaderMismatch(
                    f"legacy MCP-Protocol-Version header '{header_version}' conflicts "
                    f"with params._meta protocol version '{body_version}'"
                )
            return "legacy"
        raise MCPUnsupportedProtocolVersion(header_version)

    def _do_POST_inner(self, parsed: Any) -> None:
        if parsed.path == "/mcp":
            try:
                payload = self._read_json_body()
            except _EnvelopeError as exc:
                self._write_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": exc.code, "message": str(exc)},
                    },
                )
                return
            method = payload.get("method")
            message_id = payload.get("id")
            if not isinstance(method, str) or not method:
                self._write_json(400, {"error": "method is required"})
                return

            if method.startswith("notifications/") or message_id is None:
                # Notifications carry no response; sancho keeps no per-session
                # state, so there is nothing to process either.
                self._write_json(202, {"accepted": True})
                return

            try:
                era = self._check_mcp_headers(method, payload.get("params"))
                params = payload["params"] if "params" in payload else {}
                result = _handle_method(self.ctx, method=method, params=params, protocol_era=era)
                self._write_json(200, {"jsonrpc": "2.0", "id": message_id, "result": result})
            except Exception as exc:
                self._write_json(
                    200,
                    {"jsonrpc": "2.0", "id": message_id, "error": jsonrpc_error(exc)},
                )
            return

        if parsed.path != "/call":
            self._write_json(404, {"error": "not found"})
            return
        try:
            payload = self._read_json_body()
        except _EnvelopeError as exc:
            self._write_json(400, {"error": str(exc)})
            return
        try:
            result = _handle_method(self.ctx, method="tools/call", params=payload)
            self._write_json(200, result)
        except Exception as exc:
            self._write_json(400, {"error": str(exc)})


def serve_http(
    workspace_root: Path,
    host: str,
    port: int,
    *,
    policy: MCPPolicy | None = None,
    quick_mode: bool = False,
    quick_profile: str | None = None,
    quick_targets: list[str] | tuple[str, ...] | None = None,
    quick_modules: list[str] | tuple[str, ...] | None = None,
) -> None:
    ctx = _build_context(
        workspace_root=workspace_root,
        policy=policy,
        quick_mode=quick_mode,
        quick_profile=quick_profile,
        quick_targets=quick_targets,
        quick_modules=quick_modules,
    )
    _HttpHandler.ctx = ctx
    server = ThreadingHTTPServer((host, port), _HttpHandler)
    print(f"Sancho Fetch MCP HTTP adapter listening at http://{host}:{port}")
    server.serve_forever()


__all__ = ["MCPContext", "MCPPolicy", "_handle_method", "serve_http", "serve_stdio"]
