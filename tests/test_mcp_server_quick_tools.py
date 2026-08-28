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
        lambda workspace_root, module_id, input_payload: SimpleNamespace(
            status="ok",
            cache_status="fetched_api",
            record_dirs=[],
            output={"module_id": module_id, "ok": True},
        ),
    )

    ctx = MCPContext(
        workspace_root=Path("."),
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.test"}),
        quick_mode=True,
        quick_profile="lean",
        quick_targets=("pack.global_economic",),
        quick_modules=("fetch.test",),
    )

    tools_payload = _handle_method(ctx, "tools/list", {})
    names = _tool_names(tools_payload)
    # Published under the MCP-safe name; the dotted id is not exposed.
    assert "fetch_test" in names
    assert "fetch.test" not in names
    assert "gov_catalog" in names
    assert "gov_fetch" in names
    assert "analyze_summary" not in names
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
    assert parsed["output_preview"]["ok"] is True
    # The raw dataset is never returned over MCP -- only the preview.
    assert "output" not in parsed
    # No record dirs -> no exported file, and the note must say so instead of
    # pointing at a null primary_output_path.
    assert parsed["primary_output_path"] is None
    assert "No working file" in parsed["note"]


def test_output_preview_caps_rows_and_chars() -> None:
    from sancho.mcp.high_level_handlers import _output_preview

    rows = [{"i": i} for i in range(500)]
    assert len(_output_preview(rows)) == 20
    capped = _output_preview({"rows": rows, "source": "x"})
    assert len(capped["rows"]) == 20 and capped["source"] == "x"
    # Every top-level list is capped ("observations", "features", ...), so a
    # big raw API passthrough is never serialized in full.
    geo = _output_preview({"features": ["x" * 100] * 500, "type": "FeatureCollection"})
    assert len(geo["features"]) == 20 and geo["type"] == "FeatureCollection"
    # Data buried deeper than one level falls back to the character cap.
    text = _output_preview({"payload": {"deep": ["x" * 100] * 500}})
    assert isinstance(text, str) and len(text) == 4_000
    assert _output_preview(None) is None


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
        return SimpleNamespace(
            status="ok",
            cache_status="fetched_api",
            record_dirs=[],
            output={"ok": True, "module_id": module_id, "payload": input_payload},
        )

    monkeypatch.setattr("sancho.mcp.tool_specs.run_module", fake_run_module)

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.world_bank"}),
        quick_mode=True,
        quick_profile="lean",
        quick_targets=("pack.global_economic",),
        quick_modules=("fetch.world_bank",),
    )

    tools_payload = _handle_method(ctx, "tools/list", {})
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
    assert parsed["output_preview"]["ok"] is True
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
