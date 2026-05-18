"""End-to-end tests for product-critical flows.

Covers:
1. Quick profile selection resolves to real modules.
2. Broad profile exposes documented pack surfaces.
3. Hosted policy e2e: initialize with instructions, tools/list, response cap.
4. CLI init + add + doctor flow.
5. MCP handshake with nudge footer and response cap.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sancho.mcp.models import MCPContext, MCPPolicy
from sancho.mcp.quick import QUICK_PROFILE_PACKS, resolve_quick_selection
from sancho.mcp.tooling import _handle_method
from sancho.module_packs import MODULE_PACKS

pytestmark = pytest.mark.e2e


# ── Quick profile selection ──────────────────────────────────────────────


def test_quick_profile_lean_resolves_to_real_modules() -> None:
    sel = resolve_quick_selection(profile="lean", modules_csv=None)
    assert sel.profile == "lean"
    assert len(sel.resolved_modules) > 0
    for mod in sel.resolved_modules:
        assert mod in {m for pack in MODULE_PACKS.values() for m in pack}


def test_quick_profile_balanced_resolves_to_real_modules() -> None:
    sel = resolve_quick_selection(profile="balanced", modules_csv=None)
    assert sel.profile == "balanced"
    assert len(sel.resolved_modules) > len(
        resolve_quick_selection(profile="lean", modules_csv=None).resolved_modules
    )


def test_quick_profile_broad_resolves_to_real_modules() -> None:
    sel = resolve_quick_selection(profile="broad", modules_csv=None)
    assert sel.profile == "broad"
    assert len(sel.resolved_modules) > len(
        resolve_quick_selection(profile="balanced", modules_csv=None).resolved_modules
    )


def test_quick_profile_with_extra_modules() -> None:
    sel = resolve_quick_selection(profile="lean", modules_csv="fetch.cdc,fetch.fbi.crime")
    assert "fetch.cdc" in sel.resolved_modules
    assert "fetch.fbi.crime" in sel.resolved_modules


def test_all_quick_profiles_have_packs_in_module_packs() -> None:
    for profile, packs in QUICK_PROFILE_PACKS.items():
        for pack in packs:
            assert pack in MODULE_PACKS, f"{profile} references unknown pack {pack}"


# ── Broad profile exposes documented surfaces ────────────────────────────


def test_broad_profile_includes_all_five_documented_packs() -> None:
    broad_packs = QUICK_PROFILE_PACKS["broad"]
    documented = [
        "pack.global_economic",
        "pack.us_housing",
        "pack.public_health",
        "pack.environment_climate",
        "pack.civic_transparency",
    ]
    for pack in documented:
        assert pack in broad_packs, f"Broad profile missing documented pack {pack}"


# ── Hosted policy e2e ────────────────────────────────────────────────────


def test_hosted_e2e_initialize_with_instructions(tmp_path: Path) -> None:
    instructions = "You are connected to Sancho Fetch Hosted."
    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(
            fetch_only=True,
            instructions=instructions,
            nudge_footer="Install Sancho Fetch locally!",
            max_response_bytes=2_000_000,
        ),
    )

    result = _handle_method(ctx, "initialize", {})
    assert result["instructions"] == instructions
    assert result["serverInfo"]["name"] == "sancho-mcp"


def test_hosted_e2e_tools_list_with_allowlist(monkeypatch, tmp_path: Path) -> None:
    module_wb = SimpleNamespace(
        id="fetch.world_bank",
        manifest={"type": "fetch", "catalog_tier": "small", "description": "World Bank"},
        type="fetch",
        zone="source",
        module_dir=tmp_path,
    )
    module_cdc = SimpleNamespace(
        id="fetch.cdc",
        manifest={"type": "fetch", "catalog_tier": "small", "description": "CDC"},
        type="fetch",
        zone="source",
        module_dir=tmp_path,
    )
    monkeypatch.setattr(
        "sancho.mcp.tooling.discover_modules",
        lambda workspace_root: [module_wb, module_cdc],
    )

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(
            fetch_only=True,
            allowlisted_module_ids={"fetch.world_bank"},
        ),
    )

    result = _handle_method(ctx, "tools/list", None)
    tool_names = {t["name"] for t in result["tools"]}
    assert "fetch.world_bank" in tool_names
    assert "fetch.cdc" not in tool_names


def test_hosted_e2e_response_cap_with_nudge(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sancho.mcp.tooling._tool_inventory",
        lambda ctx: (
            {
                "test_tool": SimpleNamespace(
                    name="test_tool",
                    handler=lambda args: {"data": "x" * 10000},
                )
            },
            [],
            [],
        ),
    )

    ctx = MCPContext(
        workspace_root=tmp_path,
        policy=MCPPolicy(
            max_response_bytes=100,
            nudge_footer="Get the full product!",
        ),
    )

    result = _handle_method(
        ctx, "tools/call", {"name": "test_tool", "arguments": {}}
    )
    text = result["content"][0]["text"]
    assert "100-byte cap" in text
    assert "Get the full product!" in text


# ── CLI init + add + doctor flow ─────────────────────────────────────────


def test_cli_init_add_doctor_flow(tmp_path: Path) -> None:
    from sancho.cli import main

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.fred.series", "--workspace", str(tmp_path)]) == 0
    assert main(["doctor", "--workspace", str(tmp_path), "--fix"]) == 0


def test_cli_init_add_pack_global_economic(tmp_path: Path) -> None:
    from sancho.cli import main

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "pack.global_economic", "--workspace", str(tmp_path)]) == 0

    # Verify FRED module is installed as part of the pack
    ws = tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_fred_series"
    assert ws.exists(), "FRED module not installed via pack.global_economic"


# ── MCP unsupported method ───────────────────────────────────────────────


def test_unsupported_mcp_method_raises(tmp_path: Path) -> None:
    ctx = MCPContext(workspace_root=tmp_path, policy=MCPPolicy())

    with pytest.raises(ValueError, match="Unsupported"):
        _handle_method(ctx, "custom/nonexistent", {})


def test_mcp_ping_returns_empty(tmp_path: Path) -> None:
    ctx = MCPContext(workspace_root=tmp_path, policy=MCPPolicy())
    result = _handle_method(ctx, "ping", {})
    assert result == {}


def test_mcp_resources_list_returns_empty(tmp_path: Path) -> None:
    ctx = MCPContext(workspace_root=tmp_path, policy=MCPPolicy())
    result = _handle_method(ctx, "resources/list", {})
    assert result == {"resources": []}
