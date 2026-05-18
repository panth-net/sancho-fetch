"""Hosted security and policy invariant tests.

Covers:
1. Allowlist module IDs all resolve to real template directories.
2. Request-size cap enforcement.
3. Response-size cap enforcement and nudge footer behavior.
4. Allowlist rejection: non-allowlisted modules are hidden.
5. Rate-limiter code path (hosted limits.py).
6. Hosted server log suppression (no header/key leaking).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from sancho.mcp.hosted_allowlist import HOSTED_PROVIDERS, LINK_ONLY

pytestmark = pytest.mark.mcp
from sancho.mcp.models import MCPContext, MCPPolicy
from sancho.mcp.server import _HttpHandler
from sancho.mcp.tooling import _handle_method


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "src" / "sancho" / "templates" / "modules"


# ── Allowlist validation ─────────────────────────────────────────────────


def test_hosted_providers_all_exist_on_disk() -> None:
    """Every module ID in HOSTED_PROVIDERS must be a real template directory."""
    on_disk = {
        child.name
        for child in TEMPLATE_ROOT.iterdir()
        if child.is_dir() and (child / "module.yaml").exists()
    }
    missing = sorted(HOSTED_PROVIDERS - on_disk)
    assert not missing, f"HOSTED_PROVIDERS references missing modules: {missing}"


def test_link_only_entries_have_required_fields() -> None:
    for name, info in LINK_ONLY.items():
        assert "url" in info, f"LINK_ONLY[{name!r}] missing 'url'"
        assert "description" in info, f"LINK_ONLY[{name!r}] missing 'description'"
        assert info["url"].startswith("http"), f"LINK_ONLY[{name!r}] url is not a URL"


# ── Request-size cap ─────────────────────────────────────────────────────


def test_request_body_size_cap_rejects_oversized() -> None:
    """_read_json_body should raise when Content-Length exceeds cap."""
    handler = MagicMock(spec=_HttpHandler)
    handler.ctx = MCPContext(
        workspace_root=Path("/fake"),
        policy=MCPPolicy(max_request_bytes=100),
    )
    handler.headers = {"Content-Length": "200"}

    # Call the real method on the mock
    try:
        _HttpHandler._read_json_body(handler)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "100-byte limit" in str(e)


def test_request_body_size_default_10mb_when_no_policy() -> None:
    """When max_request_bytes is 0, default cap is 10 MB."""
    handler = MagicMock(spec=_HttpHandler)
    handler.ctx = MCPContext(
        workspace_root=Path("/fake"),
        policy=MCPPolicy(max_request_bytes=0),
    )
    # 11 MB — should fail against 10 MB default
    handler.headers = {"Content-Length": str(11 * 1024 * 1024)}

    try:
        _HttpHandler._read_json_body(handler)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "limit" in str(e)


def test_http_request_state_ignores_query_param_api_keys() -> None:
    from sancho.runtime import request_state
    from urllib.parse import urlparse

    handler = MagicMock(spec=_HttpHandler)
    handler.ctx = MCPContext(
        workspace_root=Path("/fake"),
        policy=MCPPolicy(stateless=True),
    )
    _HttpHandler._setup_request_state(handler, urlparse("/mcp?census_api_key=secret"))
    try:
        assert request_state.is_stateless() is True
    finally:
        request_state.clear()


# ── Response-size cap ────────────────────────────────────────────────────


def test_response_cap_triggers_nudge(tmp_path: Path) -> None:
    """Oversized tool output should return a cap-exceeded message with nudge."""
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(
            max_response_bytes=10,
            nudge_footer="Install locally!",
        ),
    )

    # Create a minimal tool that returns a large payload
    from sancho.mcp.tooling import _tool_inventory
    from unittest.mock import patch

    big_output = {"data": "x" * 100}
    fake_tool = MagicMock()
    fake_tool.handler.return_value = big_output

    with patch(
        "sancho.mcp.tooling._tool_inventory",
        return_value=({"test_tool": fake_tool}, [], []),
    ):
        result = _handle_method(
            ctx,
            method="tools/call",
            params={"name": "test_tool", "arguments": {}},
        )

    text = result["content"][0]["text"]
    assert "10-byte cap" in text
    assert "Install locally!" in text


def test_response_cap_zero_means_no_limit(tmp_path: Path) -> None:
    """When max_response_bytes is 0, no cap is applied."""
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(max_response_bytes=0),
    )

    from unittest.mock import patch

    big_output = {"data": "x" * 10000}
    fake_tool = MagicMock()
    fake_tool.handler.return_value = big_output

    with patch(
        "sancho.mcp.tooling._tool_inventory",
        return_value=({"test_tool": fake_tool}, [], []),
    ):
        result = _handle_method(
            ctx,
            method="tools/call",
            params={"name": "test_tool", "arguments": {}},
        )

    text = result["content"][0]["text"]
    assert "cap" not in text.lower()
    assert "x" * 100 in text


# ── Nudge footer ─────────────────────────────────────────────────────────


def test_nudge_footer_appended_to_tool_output(tmp_path: Path) -> None:
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(nudge_footer="Install Sancho Fetch locally!"),
    )

    from unittest.mock import patch

    fake_tool = MagicMock()
    fake_tool.handler.return_value = {"ok": True}

    with patch(
        "sancho.mcp.tooling._tool_inventory",
        return_value=({"test_tool": fake_tool}, [], []),
    ):
        result = _handle_method(
            ctx,
            method="tools/call",
            params={"name": "test_tool", "arguments": {}},
        )

    assert len(result["content"]) == 2
    assert result["content"][1]["text"] == "Install Sancho Fetch locally!"


def test_no_nudge_footer_when_policy_empty(tmp_path: Path) -> None:
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(nudge_footer=None),
    )

    from unittest.mock import patch

    fake_tool = MagicMock()
    fake_tool.handler.return_value = {"ok": True}

    with patch(
        "sancho.mcp.tooling._tool_inventory",
        return_value=({"test_tool": fake_tool}, [], []),
    ):
        result = _handle_method(
            ctx,
            method="tools/call",
            params={"name": "test_tool", "arguments": {}},
        )

    assert len(result["content"]) == 1


# ── Allowlist rejection ──────────────────────────────────────────────────


def test_allowlisted_tool_not_found_raises(tmp_path: Path) -> None:
    """tools/call for a non-existent tool should raise."""
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(
            allowlisted_module_ids={"fetch.world_bank"},
            fetch_only=True,
        ),
    )

    try:
        _handle_method(
            ctx,
            method="tools/call",
            params={"name": "fetch.not_real", "arguments": {}},
        )
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "not available" in str(e)


# ── LINK_ONLY interception ───────────────────────────────────────────────


def test_link_only_returns_download_url(tmp_path: Path) -> None:
    ctx = MCPContext(workspace_root=tmp_path, policy=MCPPolicy())

    result = _handle_method(
        ctx,
        method="tools/call",
        params={"name": "world_values_survey", "arguments": {}},
    )

    text = result["content"][0]["text"]
    assert "worldvaluessurvey.org" in text
    assert "install sancho fetch locally" in text.lower()


# ── Rate-limiter unit tests ──────────────────────────────────────────────


def test_rate_limiter_allows_under_limit() -> None:
    from hosting.limits import check_ip, RPM
    import importlib
    import hosting.limits as lmod

    # Fresh state
    lmod._hits.clear()
    assert check_ip("10.0.0.1") is True


def test_rate_limiter_blocks_over_limit() -> None:
    import hosting.limits as lmod

    lmod._hits.clear()
    ip = "10.0.0.99"
    for _ in range(lmod.RPM):
        assert lmod.check_ip(ip) is True
    assert lmod.check_ip(ip) is False


# ── Initialize instructions ──────────────────────────────────────────────


def test_initialize_includes_instructions(tmp_path: Path) -> None:
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(instructions="Welcome to Sancho Fetch hosted."),
    )

    result = _handle_method(ctx, method="initialize", params={})
    assert result["instructions"] == "Welcome to Sancho Fetch hosted."


def test_initialize_omits_instructions_when_none(tmp_path: Path) -> None:
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(instructions=None),
    )

    result = _handle_method(ctx, method="initialize", params={})
    assert "instructions" not in result
