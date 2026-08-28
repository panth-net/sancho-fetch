"""Wire-format tests for the MCP stdio transport.

The MCP spec (every version since 2024-11-05) mandates newline-delimited JSON
over stdio: one UTF-8 JSON-RPC message per line, terminated by ``\\n``, with no
embedded newlines. Every real MCP client (Claude Desktop, Codex, Cursor,
VS Code) sends and expects this format.

Also covers the dual-era protocol behavior required by the 2026-07-28 spec:
legacy clients handshake via ``initialize``; modern clients probe
``server/discover`` and carry their protocol version in per-request ``_meta``.
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


def test_read_skips_non_json_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stray non-JSON output (e.g. a print) must be skipped, not crash the loop."""
    msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    payload = b"some stray log line\n" + json.dumps(msg).encode("utf-8") + b"\n"
    _drive_stdin(monkeypatch, payload)
    assert mcp_server._read_stdio_message() == msg


def test_read_skips_non_object_json_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid-but-non-object JSON (array/scalar) is not a JSON-RPC message and
    must be skipped — returning it would crash serve_stdio on .get()."""
    msg = {"jsonrpc": "2.0", "id": 3, "method": "ping"}
    payload = b"[1, 2, 3]\n42\n" + json.dumps(msg).encode("utf-8") + b"\n"
    _drive_stdin(monkeypatch, payload)
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


def test_stdio_legacy_era_latch_survives_modern_discover(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A legacy initialize pins legacy serialization for the whole process.

    A stray modern ``server/discover`` mid-session must be served as modern
    without flipping the latch: the legacy client's next bare request still
    gets a legacy-shaped result instead of a -32602 demanding ``_meta``.
    """
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "server/discover", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    ]
    payload = b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in requests)
    _drive_stdin(monkeypatch, payload)
    out = _capture_stdout(monkeypatch)

    mcp_server.serve_stdio(tmp_path)

    lines = out.getvalue().decode("utf-8").strip().split("\n")
    responses = {msg["id"]: msg for msg in map(json.loads, lines)}
    assert set(responses[1]["result"]) == {"protocolVersion", "capabilities", "serverInfo"}
    assert responses[2]["result"]["supportedVersions"] == ["2026-07-28"]
    assert "result" in responses[3], f"legacy client broken after discover: {responses[3]}"
    assert set(responses[3]["result"]) == {"tools"}, "legacy shape must survive a modern call"


def test_stdio_initialize_pins_legacy_even_after_discover_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The mirror order: a modern server/discover probe first, then a real
    legacy initialize. The handshake is authoritative — bare requests after it
    must be served legacy, not rejected with -32602."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
        },
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    ]
    payload = b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in requests)
    _drive_stdin(monkeypatch, payload)
    out = _capture_stdout(monkeypatch)

    mcp_server.serve_stdio(tmp_path)

    responses = {
        msg["id"]: msg
        for msg in map(json.loads, out.getvalue().decode("utf-8").strip().split("\n"))
    }
    assert responses[1]["result"]["supportedVersions"] == ["2026-07-28"]
    assert set(responses[2]["result"]) == {"protocolVersion", "capabilities", "serverInfo"}
    assert "result" in responses[3], f"legacy client broken after probe: {responses[3]}"
    assert set(responses[3]["result"]) == {"tools"}


# ---------------------------------------------------------------------------
# Protocol version negotiation (the bug that caused Claude Desktop to
# disconnect right after a successful initialize response)
# ---------------------------------------------------------------------------


from sancho.mcp.tooling import (  # noqa: E402
    _LATEST_LEGACY_MCP_PROTOCOL_VERSION,
    _SUPPORTED_MCP_PROTOCOL_VERSIONS,
    _build_context,
    _handle_method,
    _negotiate_protocol_version,
)


def _ctx(tmp_path):
    return _build_context(
        workspace_root=tmp_path,
        policy=None,
        quick_mode=False,
        quick_profile=None,
        quick_targets=None,
        quick_modules=None,
    )


@pytest.mark.parametrize(
    "version",
    [version for version in _SUPPORTED_MCP_PROTOCOL_VERSIONS if version != "2026-07-28"],
)
def test_negotiate_echoes_supported_version(version: str) -> None:
    """Per the MCP spec: if the client's version is supported, echo it back."""
    assert _negotiate_protocol_version(version) == version


def test_initialize_never_negotiates_modern_version() -> None:
    assert _negotiate_protocol_version("2026-07-28") == _LATEST_LEGACY_MCP_PROTOCOL_VERSION


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
def test_negotiate_falls_back_to_latest_legacy_for_unknown_versions(bogus: Any) -> None:
    """Unknown/missing versions on initialize must fall back to a real,
    supported handshake-era version — only legacy clients call initialize."""
    assert _negotiate_protocol_version(bogus) == _LATEST_LEGACY_MCP_PROTOCOL_VERSION


def test_supported_versions_are_real_dates() -> None:
    """Guard against future regressions that re-introduce a fake version date."""
    import re

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for version in _SUPPORTED_MCP_PROTOCOL_VERSIONS:
        assert date_pattern.match(version), f"not a date: {version!r}"
        # Sanity: no version dates from the future (this is what tripped us up).
        # The latest published MCP spec revision is 2026-07-28.
        assert version <= "2026-07-28", (
            f"{version!r} is past the latest published MCP spec; "
            f"clients reject unknown future versions"
        )


# ---------------------------------------------------------------------------
# Modern (2026-07-28) stateless behavior: server/discover, per-request _meta,
# cacheable list results, and JSON-RPC error codes.
# ---------------------------------------------------------------------------


def test_server_discover_returns_versions_and_capabilities(tmp_path) -> None:
    result = _handle_method(_ctx(tmp_path), "server/discover", {})
    assert "2026-07-28" in result["supportedVersions"]
    assert result["supportedVersions"][0] == "2026-07-28", "newest first"
    assert result["supportedVersions"] == ["2026-07-28"]
    assert result["capabilities"] == {"tools": {}}
    assert result["resultType"] == "complete"
    assert result["ttlMs"] > 0
    assert result["cacheScope"] in {"public", "private"}
    server_info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
    assert server_info["name"] == "sancho-mcp"
    assert set(result) == {
        "supportedVersions",
        "capabilities",
        "resultType",
        "ttlMs",
        "cacheScope",
        "_meta",
    }


def test_tools_list_is_cacheable_and_deterministic(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}
    first = _handle_method(ctx, "tools/list", params)
    second = _handle_method(ctx, "tools/list", params)
    assert first["ttlMs"] > 0
    assert first["cacheScope"] == "private", "local workspace results are per-user"
    assert first["resultType"] == "complete"
    names = [tool["name"] for tool in first["tools"]]
    assert names == sorted(names), "spec: deterministic order for client caching"
    assert names == [tool["name"] for tool in second["tools"]]
    assert set(first) == {"tools", "resultType", "ttlMs", "cacheScope", "_meta"}


def test_tools_carry_titles_and_annotations(tmp_path) -> None:
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}
    tools = _handle_method(_ctx(tmp_path), "tools/list", params)["tools"]
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["sancho_paths"]["annotations"]["readOnlyHint"] is True
    assert by_name["sancho_fetch_run"]["annotations"]["openWorldHint"] is True
    assert by_name["sancho_fetch_run"]["annotations"]["destructiveHint"] is False
    for tool in tools:
        assert tool["title"], f"tool {tool['name']} is missing a title"


def test_request_with_supported_meta_version_is_served(tmp_path) -> None:
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}
    result = _handle_method(_ctx(tmp_path), "tools/list", params)
    assert result["resultType"] == "complete"


def test_legacy_results_have_exact_legacy_shape(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    initialized = _handle_method(
        ctx,
        "initialize",
        {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
    )
    assert set(initialized) == {"protocolVersion", "capabilities", "serverInfo"}
    listed = _handle_method(ctx, "tools/list", {}, protocol_era="legacy")
    assert set(listed) == {"tools"}
    pinged = _handle_method(ctx, "ping", {}, protocol_era="legacy")
    assert pinged == {}
    called = _handle_method(
        ctx,
        "tools/call",
        {"name": "sancho_paths", "arguments": {}},
        protocol_era="legacy",
    )
    assert set(called) == {"content", "structuredContent"}


def test_modern_tool_call_has_exact_modern_shape(tmp_path) -> None:
    called = _handle_method(
        _ctx(tmp_path),
        "tools/call",
        {
            "name": "sancho_paths",
            "arguments": {},
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
        },
        protocol_era="modern",
    )
    assert set(called) == {
        "content",
        "structuredContent",
        "resultType",
        "_meta",
    }


@pytest.mark.parametrize("bad_params", [None, [], "bad", 42, True])
def test_non_object_params_map_to_invalid_params(tmp_path, bad_params: Any) -> None:
    from sancho.mcp.tooling import MCPInvalidParams, jsonrpc_error

    with pytest.raises(MCPInvalidParams) as excinfo:
        _handle_method(_ctx(tmp_path), "tools/list", bad_params)
    assert jsonrpc_error(excinfo.value)["code"] == -32602


def test_modern_mode_requires_version_metadata(tmp_path) -> None:
    from sancho.mcp.tooling import MCPInvalidParams

    with pytest.raises(MCPInvalidParams):
        _handle_method(_ctx(tmp_path), "tools/list", {}, protocol_era="modern")


def test_request_with_unsupported_meta_version_errors(tmp_path) -> None:
    from sancho.mcp.tooling import MCPUnsupportedProtocolVersion, jsonrpc_error

    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}}
    with pytest.raises(MCPUnsupportedProtocolVersion) as excinfo:
        _handle_method(_ctx(tmp_path), "tools/list", params)
    error = jsonrpc_error(excinfo.value)
    assert error["code"] == -32022
    assert error["data"]["requested"] == "1900-01-01"
    assert "2026-07-28" in error["data"]["supported"]


def test_unknown_method_maps_to_method_not_found(tmp_path) -> None:
    from sancho.mcp.tooling import MCPMethodNotFound, jsonrpc_error

    with pytest.raises(MCPMethodNotFound) as excinfo:
        _handle_method(_ctx(tmp_path), "no/such_method", {})
    assert jsonrpc_error(excinfo.value)["code"] == -32601


def test_unknown_tool_maps_to_invalid_params(tmp_path) -> None:
    from sancho.mcp.tooling import MCPInvalidParams, jsonrpc_error

    with pytest.raises(MCPInvalidParams) as excinfo:
        _handle_method(_ctx(tmp_path), "tools/call", {"name": "no_such_tool"})
    assert jsonrpc_error(excinfo.value)["code"] == -32602


def test_tools_call_returns_structured_content(tmp_path) -> None:
    result = _handle_method(_ctx(tmp_path), "tools/call", {"name": "sancho_paths"})
    text_payload = json.loads(result["content"][0]["text"])
    assert result["structuredContent"] == text_payload


def test_structured_content_skipped_when_response_cap_active(tmp_path) -> None:
    """structuredContent duplicates the payload; a hosted byte cap must keep
    bounding what actually ships, so capped contexts stay text-only."""
    from sancho.mcp.models import MCPPolicy

    ctx = _build_context(
        workspace_root=tmp_path,
        policy=MCPPolicy(max_response_bytes=2_000_000),
        quick_mode=False,
        quick_profile=None,
        quick_targets=None,
        quick_modules=None,
    )
    result = _handle_method(ctx, "tools/call", {"name": "sancho_paths"})
    assert "structuredContent" not in result
    assert result["content"][0]["type"] == "text"


def test_discover_probe_via_stdio(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A modern client's stdio backward-compat probe must get a DiscoverResult."""
    request = {"jsonrpc": "2.0", "id": 0, "method": "server/discover", "params": {}}
    _drive_stdin(monkeypatch, json.dumps(request).encode("utf-8") + b"\n")
    out = _capture_stdout(monkeypatch)

    mcp_server.serve_stdio(tmp_path)

    response = json.loads(out.getvalue().decode("utf-8").rstrip("\n"))
    assert response["result"]["supportedVersions"][0] == "2026-07-28"
