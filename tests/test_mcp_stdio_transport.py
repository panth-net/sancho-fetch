"""Wire-format tests for the MCP stdio transport.

The MCP spec (every version since 2024-11-05) mandates newline-delimited JSON
over stdio: one UTF-8 JSON-RPC message per line, terminated by ``\\n``, with no
embedded newlines. Every real MCP client (Claude Desktop, Codex, Cursor,
VS Code) sends and expects this format.

An earlier sancho release shipped LSP-style ``Content-Length`` framing by
mistake; this test file pins the corrected behavior and exercises the
defensive backward-compat path so the legacy format keeps working if anyone
is still calling sancho that way.
"""

from __future__ import annotations

import io
import json
import sys
from typing import Any

import pytest

from sancho.mcp import server as mcp_server

pytestmark = pytest.mark.mcp


def _drive_stdin(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> io.BytesIO:
    """Replace ``sys.stdin.buffer`` with a BytesIO seeded with ``payload``."""
    stdin = io.BytesIO(payload)
    monkeypatch.setattr(sys, "stdin", type("FakeStdin", (), {"buffer": stdin})())
    return stdin


def _capture_stdout(monkeypatch: pytest.MonkeyPatch) -> io.BytesIO:
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", type("FakeStdout", (), {"buffer": out})())
    return out


# ---------------------------------------------------------------------------
# _read_stdio_message
# ---------------------------------------------------------------------------


def test_read_ndjson_single_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Newline-delimited JSON — the MCP spec format used by Claude Desktop/Codex."""
    msg = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
    _drive_stdin(monkeypatch, json.dumps(msg).encode("utf-8") + b"\n")
    assert mcp_server._read_stdio_message() == msg


def test_read_ndjson_skips_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank lines between messages must be skipped, not treated as EOF."""
    msg = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    payload = b"\n\n" + json.dumps(msg).encode("utf-8") + b"\n"
    _drive_stdin(monkeypatch, payload)
    assert mcp_server._read_stdio_message() == msg


def test_read_ndjson_two_messages_in_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two NDJSON messages back-to-back should each parse cleanly."""
    a = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    b = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    _drive_stdin(
        monkeypatch,
        json.dumps(a).encode("utf-8") + b"\n" + json.dumps(b).encode("utf-8") + b"\n",
    )
    assert mcp_server._read_stdio_message() == a
    assert mcp_server._read_stdio_message() == b


def test_read_ndjson_returns_none_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    _drive_stdin(monkeypatch, b"")
    assert mcp_server._read_stdio_message() is None


def test_read_legacy_content_length_framing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive backward-compat: accept LSP-style Content-Length framing too."""
    msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    body = json.dumps(msg).encode("utf-8")
    framed = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body
    _drive_stdin(monkeypatch, framed)
    assert mcp_server._read_stdio_message() == msg


# ---------------------------------------------------------------------------
# _write_stdio_message
# ---------------------------------------------------------------------------


def test_write_emits_ndjson_with_trailing_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec: each message is a single line terminated by ``\\n``."""
    out = _capture_stdout(monkeypatch)
    mcp_server._write_stdio_message({"jsonrpc": "2.0", "id": 3, "result": {"ok": True}})
    raw = out.getvalue()
    assert raw.endswith(b"\n"), "stdio messages must be newline-terminated"
    assert raw.count(b"\n") == 1, "exactly one newline (no embedded newlines)"
    assert b"Content-Length" not in raw, "must NOT emit legacy LSP framing"
    assert json.loads(raw.decode("utf-8")) == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {"ok": True},
    }


def test_write_no_embedded_newlines_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """``json.dumps`` must not introduce newlines inside the body."""
    out = _capture_stdout(monkeypatch)
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 4,
        "result": {"text": "line1\nline2", "nested": {"a": [1, 2, 3]}},
    }
    mcp_server._write_stdio_message(payload)
    raw = out.getvalue()
    # The literal "\n" inside the string value gets escaped to backslash-n
    # in JSON, so the only real newline byte is the trailing terminator.
    assert raw.count(b"\n") == 1
    assert json.loads(raw.decode("utf-8")) == payload


# ---------------------------------------------------------------------------
# Full client handshake — exercises the format every real MCP client uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_name,protocol_version",
    [
        ("claude-ai", "2025-11-25"),  # Claude Desktop
        ("codex", "2025-06-18"),  # OpenAI Codex CLI
        ("cursor", "2025-03-26"),  # Cursor
        ("vscode", "2024-11-05"),  # VS Code MCP
    ],
)
def test_initialize_handshake_via_stdio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    client_name: str,
    protocol_version: str,
) -> None:
    """End-to-end NDJSON ``initialize`` handshake from each major MCP client.

    Drives ``serve_stdio`` with a single NDJSON ``initialize`` request, then
    closes stdin. The server must read the request, dispatch it, write a
    JSON-RPC response (newline-terminated, no LSP framing), and exit cleanly.
    """
    request = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": "1.0"},
        },
    }
    _drive_stdin(monkeypatch, json.dumps(request).encode("utf-8") + b"\n")
    out = _capture_stdout(monkeypatch)

    # serve_stdio needs a workspace; an empty tmp_path is fine for the
    # initialize call (it never touches modules).
    mcp_server.serve_stdio(tmp_path)

    raw = out.getvalue()
    assert raw, f"server returned nothing for {client_name}"
    assert raw.endswith(b"\n"), "response must be newline-terminated NDJSON"
    assert b"Content-Length" not in raw, "must NOT emit legacy LSP framing"
    response = json.loads(raw.decode("utf-8").rstrip("\n"))
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 0
    assert "result" in response, f"initialize failed for {client_name}: {response}"
    assert response["result"]["serverInfo"]["name"] == "sancho-mcp"
    # The spec requires the server to echo the client's protocol version when
    # it is supported. Returning an unknown version (e.g. a future date)
    # causes Claude Desktop to disconnect right after the response.
    assert response["result"]["protocolVersion"] == protocol_version


# ---------------------------------------------------------------------------
# Protocol version negotiation (the bug that caused Claude Desktop to
# disconnect right after a successful initialize response)
# ---------------------------------------------------------------------------


from sancho.mcp.tooling import (  # noqa: E402
    _LATEST_MCP_PROTOCOL_VERSION,
    _SUPPORTED_MCP_PROTOCOL_VERSIONS,
    _negotiate_protocol_version,
)


@pytest.mark.parametrize("version", _SUPPORTED_MCP_PROTOCOL_VERSIONS)
def test_negotiate_echoes_supported_version(version: str) -> None:
    """Per the MCP spec: if the client's version is supported, echo it back."""
    assert _negotiate_protocol_version(version) == version


@pytest.mark.parametrize(
    "bogus",
    [
        "2026-03-26",  # a future/fictional version (the original bug)
        "9999-99-99",
        "",
        None,
        123,
        {"protocolVersion": "2025-11-25"},
    ],
)
def test_negotiate_falls_back_to_latest_for_unknown_versions(bogus: Any) -> None:
    """Unknown/missing versions must fall back to a real, supported version."""
    assert _negotiate_protocol_version(bogus) == _LATEST_MCP_PROTOCOL_VERSION


def test_supported_versions_are_real_dates() -> None:
    """Guard against future regressions that re-introduce a fake version date."""
    import re

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for version in _SUPPORTED_MCP_PROTOCOL_VERSIONS:
        assert date_pattern.match(version), f"not a date: {version!r}"
        # Sanity: no version dates from the future (this is what tripped us up).
        # The latest real MCP spec as of 2025-11-25 is the same string.
        assert version <= "2025-11-25", (
            f"{version!r} is past the latest published MCP spec; "
            f"clients reject unknown future versions"
        )
