"""Smoke test simulating the Claude Desktop MCP handshake: initialize -> tools/list -> tools/call."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sancho.mcp.server import MCPContext, MCPPolicy, _handle_method

pytestmark = [pytest.mark.mcp, pytest.mark.e2e]


def test_claude_desktop_handshake_initialize_list_call(monkeypatch, tmp_path: Path) -> None:
    module = SimpleNamespace(
        id="fetch.world_bank",
        manifest={"type": "fetch", "catalog_tier": "large", "description": "World Bank"},
        type="fetch",
        zone="source",
        module_dir=tmp_path,
    )
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: [module])
    monkeypatch.setattr(
        "sancho.mcp.tooling.load_provider_catalog",
        lambda module_dir, **_: {
            "provider": "fetch.world_bank",
            "families": [
                {
                    "id": "country.indicator",
                    "base_aliases": ["v2"],
                    "path_templates": ["/country/{country}/indicator/{indicator}"],
                    "methods": ["GET"],
                },
            ],
        },
    )
    monkeypatch.setattr(
        "sancho.mcp.tool_specs.run_module",
        lambda workspace_root, module_id, input_payload: SimpleNamespace(
            output={"provider": module_id, "rows": 10, "retrieved_at": "2026-04-01T00:00:00Z"}
        ),
    )

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.world_bank"}),
        quick_mode=True,
        quick_profile="lean",
        quick_targets=("pack.global_economic",),
        quick_modules=("fetch.world_bank",),
    )

    # Step 1: initialize
    init_result = _handle_method(ctx, "initialize", {})
    assert init_result["serverInfo"]["name"] == "sancho-mcp"
    assert "protocolVersion" in init_result

    # Step 2: tools/list
    tools_result = _handle_method(ctx, "tools/list", None)
    tool_names = [t["name"] for t in tools_result["tools"]]
    assert "gov_catalog" in tool_names
    assert "gov_fetch" in tool_names
    assert "fetch.world_bank" in tool_names

    # Step 3: tools/call gov_catalog (list available modules)
    catalog_result = _handle_method(ctx, "tools/call", {"name": "gov_catalog", "arguments": {}})
    catalog_text = catalog_result["content"][0]["text"]
    assert "world_bank" in catalog_text

    # Step 4: tools/call a family alias (simulate actual data fetch)
    alias_result = _handle_method(
        ctx,
        "tools/call",
        {
            "name": "gov_world_bank__country_indicator",
            "arguments": {"country": "all", "indicator": "SP.POP.TOTL", "params": {"format": "json"}},
        },
    )
    parsed = json.loads(alias_result["content"][0]["text"])
    assert parsed["provider"] == "fetch.world_bank"
    assert parsed["rows"] == 10
