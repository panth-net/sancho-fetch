from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.mcp

from sancho.mcp.server import MCPContext, MCPPolicy, _handle_method


def _tool_names(payload: dict) -> list[str]:
    tools = payload.get("tools", [])
    return sorted([str(tool.get("name")) for tool in tools if isinstance(tool, dict)])


def test_quick_mode_policy_filters_tools_and_enforces_call_allowlist(monkeypatch) -> None:
    modules = [
        SimpleNamespace(
            id="fetch.test",
            manifest={"type": "fetch", "catalog_tier": "small", "description": "Fetch test"},
            type="fetch",
            zone="source",
            module_dir=Path("."),
        ),
        SimpleNamespace(
            id="analyze.summary",
            manifest={"type": "analyze", "description": "Analyze summary"},
            type="analyze",
            zone="source",
            module_dir=Path("."),
        ),
    ]

    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: modules)
    monkeypatch.setattr(
        "sancho.mcp.tool_specs.run_module",
        lambda workspace_root, module_id, input_payload: SimpleNamespace(output={"module_id": module_id, "ok": True}),
    )

    ctx = MCPContext(
        workspace_root=Path("."),
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.test"}),
        quick_mode=True,
        quick_profile="lean",
        quick_targets=("pack.global_economic",),
        quick_modules=("fetch.test",),
    )

    tools_payload = _handle_method(ctx, "tools/list", None)
    names = _tool_names(tools_payload)
    assert "fetch.test" in names
    assert "gov_catalog" in names
    assert "gov_fetch" in names
    assert "analyze.summary" not in names

    with pytest.raises(ValueError) as exc_info:
        _handle_method(
            ctx,
            "tools/call",
            {"name": "analyze.summary", "arguments": {}},
        )
    assert "not available" in str(exc_info.value)

    call_payload = _handle_method(
        ctx,
        "tools/call",
        {"name": "fetch.test", "arguments": {"x": 1}},
    )
    content = call_payload["content"][0]["text"]
    parsed = json.loads(content)
    assert parsed["module_id"] == "fetch.test"
    assert parsed["ok"] is True


def test_quick_mode_generates_family_aliases_and_executes_binding(monkeypatch, tmp_path: Path) -> None:
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
                    "id": "dup.family",
                    "base_aliases": ["v1"],
                    "path_templates": ["/dup/{key}"],
                    "methods": ["GET"],
                },
                {
                    "id": "dup-family",
                    "base_aliases": ["v1"],
                    "path_templates": ["/dup/{key}"],
                    "methods": ["GET"],
                },
                {
                    "id": "country.indicator",
                    "base_aliases": ["v2"],
                    "path_templates": ["/country/{country}/indicator/{indicator}"],
                    "methods": ["GET"],
                },
            ],
        },
    )

    captured: dict[str, object] = {}

    def fake_run_module(workspace_root, module_id, input_payload):
        captured["module_id"] = module_id
        captured["payload"] = input_payload
        return SimpleNamespace(output={"ok": True, "module_id": module_id, "payload": input_payload})

    monkeypatch.setattr("sancho.mcp.tool_specs.run_module", fake_run_module)

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.world_bank"}),
        quick_mode=True,
        quick_profile="lean",
        quick_targets=("pack.global_economic",),
        quick_modules=("fetch.world_bank",),
    )

    tools_payload = _handle_method(ctx, "tools/list", None)
    names = _tool_names(tools_payload)
    assert "gov_world_bank__dup_family" in names
    assert "gov_world_bank__dup_family_2" in names

    alias_name = "gov_world_bank__country_indicator"
    assert alias_name in names

    call_result = _handle_method(
        ctx,
        "tools/call",
        {
            "name": alias_name,
            "arguments": {
                "country": "all",
                "indicator": "SP.POP.TOTL",
                "params": {"format": "json"},
                "body": {"debug": True},
            },
        },
    )
    parsed = json.loads(call_result["content"][0]["text"])
    assert parsed["ok"] is True
    assert captured["module_id"] == "fetch.world_bank"
    assert captured["payload"] == {
        "method": "GET",
        "base": "v2",
        "path": "/country/all/indicator/SP.POP.TOTL",
        "params": {"format": "json"},
        "body": {"debug": True},
    }

    with pytest.raises(ValueError) as exc_info:
        _handle_method(
            ctx,
            "tools/call",
            {"name": alias_name, "arguments": {"country": "all"}},
        )
    assert "requires 'indicator'" in str(exc_info.value)
