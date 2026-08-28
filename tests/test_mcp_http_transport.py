from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from sancho.mcp.server import _HttpHandler
from sancho.mcp.tooling import _build_context


@pytest.fixture
def mcp_url(tmp_path: Path):
    _HttpHandler.ctx = _build_context(
        workspace_root=tmp_path,
        policy=None,
        quick_mode=False,
        quick_profile=None,
        quick_targets=None,
        quick_modules=None,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/mcp"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post(url: str, payload: dict, *, headers: dict[str, str] | None = None) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read())


@pytest.mark.parametrize("params", [None, [], "bad", 42, True])
def test_http_non_object_params_are_invalid_params(mcp_url: str, params: object) -> None:
    response = _post(
        mcp_url,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": params},
    )
    assert response == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32602, "message": "params must be a JSON object when present"},
    }


def test_http_missing_params_is_distinct_from_explicit_null(mcp_url: str) -> None:
    missing = _post(mcp_url, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
    null = _post(mcp_url, {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": None})
    assert missing == {"jsonrpc": "2.0", "id": 2, "result": {}}
    assert null["error"]["code"] == -32602


def test_modern_http_requires_matching_version_header(mcp_url: str) -> None:
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}
    missing = _post(
        mcp_url,
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": params},
    )
    assert missing["error"]["code"] == -32020

    response = _post(
        mcp_url,
        {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": params},
        headers={"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"},
    )
    assert response["result"]["resultType"] == "complete"
    assert response["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "sancho-mcp"


def test_http_discovery_bootstraps_without_cross_era_fields(mcp_url: str) -> None:
    response = _post(
        mcp_url,
        {"jsonrpc": "2.0", "id": 6, "method": "server/discover", "params": {}},
        headers={"MCP-Protocol-Version": "2026-07-28"},
    )
    assert response["result"]["supportedVersions"] == ["2026-07-28"]


def _raw_post(
    url: str,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
    content_length: int | None = None,
) -> tuple[int, dict]:
    """POST arbitrary bytes, tolerating non-200 responses.

    ``content_length`` overrides the header without sending that many bytes,
    so oversized-declaration handling can be tested without a huge payload.
    """
    import http.client
    from urllib.parse import urlparse

    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        conn.putrequest("POST", parsed.path)
        conn.putheader("Content-Type", "application/json")
        conn.putheader(
            "Content-Length",
            str(content_length if content_length is not None else len(body)),
        )
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        conn.endheaders()
        if content_length is None:
            conn.send(body)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


def test_legacy_http_client_with_required_version_header(mcp_url: str) -> None:
    """Since 2025-06-18 legacy streamable-HTTP clients MUST send
    MCP-Protocol-Version on every request; that must never be a mismatch."""
    headers = {"MCP-Protocol-Version": "2025-06-18"}
    initialized = _post(
        mcp_url,
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}},
        },
        headers=headers,
    )
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert set(initialized["result"]) == {"protocolVersion", "capabilities", "serverInfo"}

    listed = _post(
        mcp_url,
        {"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}},
        headers=headers,
    )
    assert set(listed["result"]) == {"tools"}, "legacy result must carry no modern fields"


def test_legacy_header_conflicting_with_modern_meta_is_rejected(mcp_url: str) -> None:
    response = _post(
        mcp_url,
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/list",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
        },
        headers={"MCP-Protocol-Version": "2025-06-18"},
    )
    assert response["error"]["code"] == -32020


def test_unsupported_version_header_is_rejected(mcp_url: str) -> None:
    response = _post(
        mcp_url,
        {"jsonrpc": "2.0", "id": 13, "method": "tools/list", "params": {}},
        headers={"MCP-Protocol-Version": "2031-01-01"},
    )
    assert response["error"]["code"] == -32022


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"{not json", -32700),
        (b'[{"jsonrpc": "2.0", "id": 1, "method": "ping"}]', -32600),  # batch
        (b"42", -32600),
        (b'"tools/list"', -32600),
    ],
)
def test_http_envelope_rejections_are_deterministic(mcp_url: str, body: bytes, code: int) -> None:
    """Garbage bodies get a JSON-RPC error, never a traceback or dropped socket."""
    status, payload = _raw_post(mcp_url, body)
    assert status == 400
    assert payload["error"]["code"] == code
    assert payload["id"] is None


def test_http_oversized_body_declaration_is_rejected(mcp_url: str) -> None:
    status, payload = _raw_post(mcp_url, b"", content_length=50 * 1024 * 1024)
    assert status == 400
    assert payload["error"]["code"] == -32600
    assert "exceeds" in payload["error"]["message"]

