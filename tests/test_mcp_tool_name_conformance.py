"""Guards that every MCP-published tool name conforms to Anthropic's pattern.

The MCP / Anthropic API requires tool names to match ^[a-zA-Z0-9_-]{1,64}$.
Sancho's internal module ids use dots (fetch.census.acs_profile) and family
aliases can exceed 64 chars, so names are normalized at the MCP boundary. These
tests pin that contract and the back-compat dispatch on the original dotted id.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.mcp

from sancho.mcp.server import MCPContext, MCPPolicy, _handle_method
from sancho.mcp.tool_specs import mcp_tool_name, unique_tool_name

NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _mod(module_id: str, mtype: str = "fetch", tier: str = "small", **manifest):
    base: dict = {"type": mtype, "description": module_id}
    if mtype == "fetch":
        base["catalog_tier"] = tier
    base.update(manifest)
    return SimpleNamespace(
        id=module_id,
        manifest=base,
        type=mtype,
        zone="source",
        module_dir=Path("."),
    )


def _names(ctx: MCPContext) -> list[str]:
    payload = _handle_method(ctx, "tools/list", None)
    return [t["name"] for t in payload["tools"]]


# --- helper unit checks --------------------------------------------------


def test_mcp_tool_name_is_char_safe_and_capped() -> None:
    assert mcp_tool_name("fetch.census.acs_profile") == "fetch_census_acs_profile"
    assert mcp_tool_name("fetch.world_bank") == "fetch_world_bank"
    assert mcp_tool_name("analyze.summary") == "analyze_summary"
    # empty / all-illegal falls back so length is never 0
    assert mcp_tool_name("") == "tool"
    assert mcp_tool_name("...") == "___"
    capped = mcp_tool_name("fetch." + "x" * 200)
    assert len(capped) == 64
    assert NAME_RE.fullmatch(capped)


def test_unique_tool_name_dedupes_within_64() -> None:
    used: set[str] = set()
    base = "g" * 64
    first = unique_tool_name(base, used)
    used.add(first)
    assert first == base
    second = unique_tool_name(base, used)
    used.add(second)
    third = unique_tool_name(base, used)
    assert len({first, second, third}) == 3
    for name in (second, third):
        assert len(name) <= 64
        assert NAME_RE.fullmatch(name)


# --- published-name conformance -----------------------------------------


def test_all_published_names_conform_non_quick(monkeypatch) -> None:
    modules = [
        _mod("fetch.world_bank"),
        _mod("fetch.census.acs_profile"),
        _mod("analyze.summary", mtype="analyze"),
    ]
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: modules)

    ctx = MCPContext(workspace_root=Path("."))  # default policy: non-quick, all modules
    names = _names(ctx)

    assert names
    for name in names:
        assert NAME_RE.fullmatch(name), f"non-conformant tool name: {name!r}"
    assert not any("." in name for name in names)
    assert {"fetch_world_bank", "fetch_census_acs_profile", "analyze_summary"} <= set(names)


def test_long_family_alias_is_capped(monkeypatch, tmp_path: Path) -> None:
    # A >55-char family id would mint a 65-char alias without the boundary cap.
    long_family_id = "v1.committee.by_committee_id.candidates.history.by_cycle"
    raw_uncapped = "gov_fec__" + "_".join(long_family_id.split("."))
    assert len(raw_uncapped) == 65  # sanity: this is the bug the cap prevents

    module = _mod("fetch.fec", tier="large")
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: [module])
    monkeypatch.setattr(
        "sancho.mcp.tooling.load_provider_catalog",
        lambda module_dir, **_: {
            "provider": "fetch.fec",
            "families": [
                {
                    "id": long_family_id,
                    "base_aliases": ["v1"],
                    "path_templates": ["/x/{key}"],
                    "methods": ["GET"],
                },
            ],
        },
    )

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.fec"}),
        quick_mode=True,
        quick_profile="broad",
        quick_modules=("fetch.fec",),
    )
    names = _names(ctx)

    for name in names:
        assert NAME_RE.fullmatch(name), f"non-conformant tool name: {name!r}"
    aliases = [n for n in names if n.startswith("gov_fec__")]
    assert aliases, names
    assert all(len(n) <= 64 for n in aliases)


def test_no_published_name_collides_with_link_only(monkeypatch) -> None:
    from sancho.mcp.hosted_allowlist import LINK_ONLY

    modules = [_mod("fetch.world_bank"), _mod("fetch.census.acs_profile")]
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: modules)

    ctx = MCPContext(workspace_root=Path("."))
    names = set(_names(ctx))
    assert not (names & set(LINK_ONLY))


# --- dispatch ------------------------------------------------------------


def test_safe_name_and_legacy_dotted_name_both_dispatch(monkeypatch) -> None:
    module = _mod("fetch.world_bank")
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: [module])
    monkeypatch.setattr(
        "sancho.mcp.tool_specs.run_module",
        lambda workspace_root, module_id, input_payload: SimpleNamespace(
            status="ok",
            cache_status="fetched_api",
            record_dirs=[],
            output={"module_id": module_id, "args": input_payload},
        ),
    )

    ctx = MCPContext(workspace_root=Path("."))
    for name in ("fetch_world_bank", "fetch.world_bank"):
        out = _handle_method(ctx, "tools/call", {"name": name, "arguments": {"x": 1}})
        parsed = json.loads(out["content"][0]["text"])
        # The handler always runs the real, dotted module id.
        assert parsed["module_id"] == "fetch.world_bank"
        assert parsed["output_preview"]["args"] == {"x": 1}


def test_colliding_ids_get_distinct_names_and_route_correctly(monkeypatch) -> None:
    # Both ids sanitize to "fetch_a_b"; the second must get a distinct safe name,
    # and each dotted id must still route to its own module via the raw key.
    modules = [_mod("fetch.a_b"), _mod("fetch.a.b")]
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: modules)
    monkeypatch.setattr(
        "sancho.mcp.tool_specs.run_module",
        lambda workspace_root, module_id, input_payload: SimpleNamespace(
            status="ok", cache_status="fetched_api", record_dirs=[], output={"module_id": module_id}
        ),
    )

    ctx = MCPContext(workspace_root=Path("."))
    published = [n for n in _names(ctx) if n.startswith("fetch_a")]
    assert {"fetch_a_b", "fetch_a_b_2"} <= set(published)
    for name in published:
        assert NAME_RE.fullmatch(name)

    for raw in ("fetch.a_b", "fetch.a.b"):
        out = _handle_method(ctx, "tools/call", {"name": raw, "arguments": {}})
        assert json.loads(out["content"][0]["text"])["module_id"] == raw


def test_module_cannot_shadow_reserved_core_tools(monkeypatch, tmp_path: Path) -> None:
    # Module ids that normalize onto reserved core/high-level tool names. The
    # core tools must keep their canonical names; the modules take a suffix.
    modules = [_mod("gov.catalog"), _mod("gov.fetch"), _mod("sancho.paths")]
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: modules)
    monkeypatch.setattr(
        "sancho.mcp.tool_specs.run_module",
        lambda workspace_root, module_id, input_payload: SimpleNamespace(
            status="ok", cache_status="fetched_api", record_dirs=[], output={"ran_module": module_id}
        ),
    )

    ctx = MCPContext(workspace_root=tmp_path, quick_mode=True, quick_profile="lean")
    names = _names(ctx)
    assert len(names) == len(set(names)), "published tool names must be unique"
    names_set = set(names)

    # Reserved tools keep their canonical names; shadowing modules are suffixed.
    for core, shadowed in (
        ("gov_catalog", "gov_catalog_2"),
        ("gov_fetch", "gov_fetch_2"),
        ("sancho_paths", "sancho_paths_2"),
    ):
        assert core in names_set, f"reserved core tool {core} missing"
        assert shadowed in names_set, f"shadowing module should be suffixed to {shadowed}"

    # Calling the reserved name runs the CORE tool, never the module.
    catalog = _handle_method(ctx, "tools/call", {"name": "gov_catalog", "arguments": {}})
    payload = json.loads(catalog["content"][0]["text"])
    assert "installed_modules" in payload  # catalog payload
    assert "ran_module" not in payload
    with pytest.raises(ValueError):  # core gov_fetch validates its provider arg
        _handle_method(ctx, "tools/call", {"name": "gov_fetch", "arguments": {}})

    # The module is still reachable via its original dotted id.
    module_out = _handle_method(ctx, "tools/call", {"name": "gov.catalog", "arguments": {}})
    module_payload = json.loads(module_out["content"][0]["text"])
    assert module_payload["output_preview"]["ran_module"] == "gov.catalog"


def test_catalog_module_tool_names_reflect_final_dedup(monkeypatch, tmp_path: Path) -> None:
    # Two ids normalize to the same value; the catalog must map each to the real,
    # distinct published name (not a fresh recompute that collapses them).
    modules = [_mod("fetch.a_b"), _mod("fetch.a.b")]
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: modules)

    ctx = MCPContext(workspace_root=tmp_path, quick_mode=True, quick_profile="lean")
    names = set(_names(ctx))

    catalog = _handle_method(ctx, "tools/call", {"name": "gov_catalog", "arguments": {}})
    payload = json.loads(catalog["content"][0]["text"])
    mapping = payload["module_tool_names"]

    assert set(mapping) == {"fetch.a_b", "fetch.a.b"}
    assert mapping["fetch.a_b"] != mapping["fetch.a.b"]  # not collapsed
    assert set(mapping.values()) == {"fetch_a_b", "fetch_a_b_2"}
    for module_id, tool_name in mapping.items():
        assert tool_name in names, f"catalog name {tool_name} for {module_id} not callable"


def test_family_alias_catalog_consistent_under_global_collision(monkeypatch, tmp_path: Path) -> None:
    # A non-alias module pre-claims the name the world_bank alias would mint, so
    # the alias is suffixed during global registration. The catalog must
    # advertise the suffixed, actually-callable name (Finding 3 write-back).
    wb = _mod("fetch.world_bank", tier="large")
    clash = _mod("gov.world_bank__country_indicator")  # normalizes onto the alias name
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: [wb, clash])
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

    ctx = MCPContext(workspace_root=tmp_path, quick_mode=True, quick_profile="lean")
    names = set(_names(ctx))

    catalog = _handle_method(ctx, "tools/call", {"name": "gov_catalog", "arguments": {}})
    payload = json.loads(catalog["content"][0]["text"])
    alias_names = [entry["name"] for entry in payload["aliases"]]

    assert alias_names
    assert "gov_world_bank__country_indicator" in names  # the module claimed the base
    assert "gov_world_bank__country_indicator_2" in alias_names  # alias was suffixed
    for alias_name in alias_names:
        # Catalog must never advertise a name that is not in tools/list.
        assert alias_name in names, f"catalog alias {alias_name!r} not callable"


def test_gov_catalog_alias_names_are_callable(monkeypatch, tmp_path: Path) -> None:
    module = _mod("fetch.fec", tier="large")
    monkeypatch.setattr("sancho.mcp.tooling.discover_modules", lambda workspace_root: [module])
    monkeypatch.setattr(
        "sancho.mcp.tooling.load_provider_catalog",
        lambda module_dir, **_: {
            "provider": "fetch.fec",
            "families": [
                {
                    "id": "v1.committee.by_committee_id.candidates.history.by_cycle",
                    "base_aliases": ["v1"],
                    "path_templates": ["/x/{key}"],
                    "methods": ["GET"],
                },
                {
                    "id": "short",
                    "base_aliases": ["v1"],
                    "path_templates": ["/y/{key}"],
                    "methods": ["GET"],
                },
            ],
        },
    )

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(fetch_only=True, allowlisted_module_ids={"fetch.fec"}),
        quick_mode=True,
        quick_profile="broad",
        quick_modules=("fetch.fec",),
    )
    names = set(_names(ctx))

    catalog = _handle_method(ctx, "tools/call", {"name": "gov_catalog", "arguments": {}})
    payload = json.loads(catalog["content"][0]["text"])
    alias_names = [entry["name"] for entry in payload["aliases"]]

    assert alias_names
    for alias_name in alias_names:
        # The name the catalog advertises must be exactly what tools/list exposes.
        assert alias_name in names, f"catalog alias {alias_name!r} not callable"
        assert NAME_RE.fullmatch(alias_name)
