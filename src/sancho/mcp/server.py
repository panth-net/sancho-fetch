from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sancho.mcp.models import MCPContext, MCPPolicy
from sancho.mcp.tooling import (
    MCPHeaderMismatch,
    _build_context,
    _handle_method,
    _tools_payload,
    jsonrpc_error,
)


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

    while True:
        message = _read_stdio_message()
        if message is None:
            break
        method = message.get("method")
        message_id = message.get("id")
        if not method:
            continue

        if method.startswith("notifications/"):
            continue

        try:
            result = _handle_method(ctx, method=method, params=message.get("params"))
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
        length = int(self.headers.get("Content-Length", "0"))
        # Defensive upper bound on request body size. When policy.max_request_bytes
        # is 0 (default, local/stdio/non-hosted) we still apply a generous 10 MB
        # cap so a malformed or hostile client can't exhaust memory reading an
        # unbounded body.
        max_req = self.ctx.policy.max_request_bytes or (10 * 1024 * 1024)
        if length < 0 or length > max_req:
            raise ValueError(f"Request body exceeds {max_req}-byte limit")
        body = self.rfile.read(length) if length else b"{}"
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Request payload must be a JSON object")
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

    def _check_mcp_headers(self, method: str, params: Any) -> None:
        """Validate the 2026-07-28 routing headers when the client sends them.

        Absent headers are tolerated (handshake-era clients don't send them);
        present-but-mismatched headers mean a confused gateway or client and
        must fail rather than route on the wrong value.
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

    def _do_POST_inner(self, parsed: Any) -> None:
        if parsed.path == "/mcp":
            payload = self._read_json_body()
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
                self._check_mcp_headers(method, payload.get("params"))
                result = _handle_method(self.ctx, method=method, params=payload.get("params"))
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
        payload = self._read_json_body()
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
