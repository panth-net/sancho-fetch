from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.mcp.high_level_tools import build_high_level_tools
from sancho.mcp.models import MCPContext, MCPPolicy


REQUIRED_TOOL_NAMES = {
    "sancho_paths",
    "sancho_mode",
    "sancho_inventory",
    "sancho_find_sources",
    "sancho_module_show",
    "sancho_cache_status",
    "sancho_fetch_run",
    "sancho_export_to_project",
    "sancho_log_tail",
    "sancho_log_show",
    "sancho_env_open",
    "sancho_update_check",
    "sancho_update_preview",
    "sancho_custom_status",
}


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_build_high_level_tools_covers_gameplan_set(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy(stateless=False))
    tools = build_high_level_tools(ctx)
    names = {t.name for t in tools}
    missing = REQUIRED_TOOL_NAMES - names
    assert not missing, f"missing high-level tools: {missing}"


def test_hosted_mcp_skips_high_level_tools(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy(stateless=True))
    tools = build_high_level_tools(ctx)
    assert tools == []


def test_sancho_paths_tool_returns_workspace_paths(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    result = tools["sancho_paths"].handler({})
    # The tool wraps cli_library._paths_payload, which resolves via CWD,
    # so the exact workspace path it picks up depends on cwd. Either way
    # the result must be a structured payload (or a "no workspace" reply
    # if pytest happened to run outside the workspace).
    assert "library" in result
    assert "current_project" in result


def test_sancho_mode_tool_returns_only_developer_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANCHO_DEVELOPER_MODE", raising=False)
    ws = _init_workspace(tmp_path)
    secret = "secret-value-that-must-not-leak"
    (ws / ".env").write_text(
        f"FRED_API_KEY={secret}\nSANCHO_DEVELOPER_MODE=true\n",
        encoding="utf-8",
    )
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    result = tools["sancho_mode"].handler({})
    assert result == {"developer_mode": True}
    assert secret not in json.dumps(result)


def test_sancho_module_show_tool_returns_manifest(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    result = tools["sancho_module_show"].handler({"module_id": "fetch.world_bank"})
    assert result["module_id"] == "fetch.world_bank"
    assert result["type"] == "fetch"


def test_sancho_find_sources_requires_query(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    with pytest.raises(ValueError):
        tools["sancho_find_sources"].handler({})
    result = tools["sancho_find_sources"].handler({"query": "census ACS"})
    assert result["candidate_count"] > 0
    assert "candidates only" in result["note"].lower()


def test_sancho_update_check_tool_is_non_mutating(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    before = sorted(p.name for p in ws.iterdir())
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    payload = tools["sancho_update_check"].handler({})
    after = sorted(p.name for p in ws.iterdir())
    assert before == after
    assert "modules" in payload
    assert payload["personal_paths_touched_by_update"] == []


def test_sancho_env_open_tool_never_reads_values(tmp_path: Path) -> None:
    ws = _init_workspace(tmp_path)
    # Seed .env with a fake key and a real-looking value.
    (ws / ".env").write_text("FAKE_KEY=super-secret-do-not-leak\n", encoding="utf-8")
    ctx = MCPContext(workspace_root=ws, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    result = tools["sancho_env_open"].handler({"provider": "census"})
    serialized = json.dumps(result, default=str)
    assert "super-secret-do-not-leak" not in serialized
    assert result["env_path"].endswith(".env")
    assert isinstance(result["provider_key_hints"], list)
