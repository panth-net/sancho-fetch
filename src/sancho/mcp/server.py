from __future__ import annotations

import json
import queue
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from sancho.mcp.models import MCPContext, MCPPolicy
from sancho.mcp.tooling import _build_context, _handle_method, _tools_payload


def _read_stdio_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        stripped = line.strip()
        if not stripped:
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.strip().lower()] = value.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_stdio_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
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
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "error": {"code": -32000, "message": str(exc)},
                    }
                )


class _HttpHandler(BaseHTTPRequestHandler):
    ctx: MCPContext
    sessions: dict[str, queue.Queue[dict[str, Any]]] = {}
    session_lock = threading.Lock()

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _write_sse(self, event: str, data: str) -> None:
        self.wfile.write(f"event: {event}\n".encode("utf-8"))
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))

    @classmethod
    def _create_session(cls) -> tuple[str, queue.Queue[dict[str, Any]]]:
        session_id = uuid4().hex
        channel: queue.Queue[dict[str, Any]] = queue.Queue()
        with cls.session_lock:
            cls.sessions[session_id] = channel
        return session_id, channel

    @classmethod
    def _get_session(cls, session_id: str) -> queue.Queue[dict[str, Any]] | None:
        with cls.session_lock:
            return cls.sessions.get(session_id)

    @classmethod
    def _remove_session(cls, session_id: str) -> None:
        with cls.session_lock:
            cls.sessions.pop(session_id, None)

    def _serve_sse(self) -> None:
        session_id, channel = self._create_session()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self._write_sse("endpoint", f"/messages?session_id={session_id}")
        self.wfile.flush()
        try:
            while True:
                try:
                    payload = channel.get(timeout=15.0)
                    self._write_sse("message", json.dumps(payload))
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self._remove_session(session_id)

    def _enqueue_mcp_response(self, session_id: str, payload: dict[str, Any]) -> bool:
        channel = self._get_session(session_id)
        if channel is None:
            return False
        channel.put(payload)
        return True

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
        if self.path == "/sse":
            self._serve_sse()
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self._setup_request_state(parsed)
        try:
            self._do_POST_inner(parsed)
        finally:
            self._teardown_request_state()

    def _do_POST_inner(self, parsed: Any) -> None:
        if parsed.path == "/mcp":
            payload = self._read_json_body()
            method = payload.get("method")
            message_id = payload.get("id")
            if not isinstance(method, str) or not method:
                self._write_json(400, {"error": "method is required"})
                return

            if method.startswith("notifications/") or message_id is None:
                try:
                    _handle_method(self.ctx, method=method, params=payload.get("params"))
                except Exception:
                    pass
                self._write_json(202, {"accepted": True})
                return

            try:
                result = _handle_method(self.ctx, method=method, params=payload.get("params"))
                self._write_json(200, {"jsonrpc": "2.0", "id": message_id, "result": result})
            except Exception as exc:
                self._write_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "error": {"code": -32000, "message": str(exc)},
                    },
                )
            return

        if parsed.path == "/messages":
            payload = self._read_json_body()
            session_ids = parse_qs(parsed.query).get("session_id", [])
            session_id = session_ids[0] if session_ids else ""
            if not session_id:
                self._write_json(400, {"error": "missing session_id"})
                return

            method = payload.get("method")
            message_id = payload.get("id")
            if not isinstance(method, str) or not method:
                self._write_json(400, {"error": "method is required"})
                return

            if method.startswith("notifications/") or message_id is None:
                self._write_json(202, {"accepted": True})
                return

            try:
                result = _handle_method(self.ctx, method=method, params=payload.get("params"))
                message = {"jsonrpc": "2.0", "id": message_id, "result": result}
            except Exception as exc:
                message = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32000, "message": str(exc)},
                }

            if not self._enqueue_mcp_response(session_id, message):
                self._write_json(404, {"error": "unknown session_id"})
                return
            self._write_json(202, {"accepted": True})
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


__all__ = [
    "MCPContext",
    "MCPPolicy",
    "_handle_method",
    "serve_http",
    "serve_stdio",
]
