from __future__ import annotations

from pathlib import Path

import pytest

from sancho.cli import main
from sancho.mcp.quick import QuickSelection, QuickWorkspaceState

pytestmark = pytest.mark.mcp


def _quick_state(tmp_path: Path) -> QuickWorkspaceState:
    selection = QuickSelection(
        profile="lean",
        profile_targets=["pack.global_economic"],
        override_tokens=["world_bank"],
        resolved_targets=["pack.global_economic", "fetch.world_bank"],
        resolved_modules=["fetch.world_bank", "fetch.bls"],
    )
    return QuickWorkspaceState(
        quick_home=tmp_path,
        workspace_root=tmp_path / "sancho-workspace",
        selection=selection,
        installed_module_ids=["fetch.world_bank"],
        allowlisted_fetch_module_ids=["fetch.world_bank", "fetch.bls"],
    )


def test_mcp_serve_quick_bootstraps_and_applies_policy(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    state = _quick_state(tmp_path)

    def fake_ensure_quick_workspace(**kwargs):
        calls["ensure"] = kwargs
        return state

    def fake_serve_stdio(workspace_root, **kwargs):
        calls["serve_stdio"] = {"workspace_root": workspace_root, **kwargs}

    monkeypatch.setattr("sancho.cli_mcp_commands.ensure_quick_workspace", fake_ensure_quick_workspace)
    monkeypatch.setattr("sancho.cli_mcp_commands.serve_stdio", fake_serve_stdio)

    assert main(["mcp", "serve", "--quick", "--profile", "lean", "--modules", "world_bank"]) == 0
    ensure_kwargs = calls["ensure"]
    assert ensure_kwargs["profile"] == "lean"
    assert ensure_kwargs["modules_csv"] == "world_bank"
    assert ensure_kwargs["install_targets"] is True

    serve_kwargs = calls["serve_stdio"]
    assert serve_kwargs["workspace_root"] == state.workspace_root
    assert serve_kwargs["quick_mode"] is True
    assert serve_kwargs["quick_profile"] == "lean"
    policy = serve_kwargs["policy"]
    assert policy.fetch_only is True
    assert policy.allowlisted_module_ids == {"fetch.world_bank", "fetch.bls"}


def test_mcp_config_quick_writes_quick_command_snippet(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    state = _quick_state(tmp_path)
    quick_home = tmp_path / "quick-home"

    def fake_ensure_quick_workspace(**kwargs):
        calls["ensure"] = kwargs
        return state

    def fake_write_client_config(**kwargs):
        calls["write"] = kwargs
        return tmp_path / "config.json"

    monkeypatch.setattr("sancho.cli_mcp_commands.ensure_quick_workspace", fake_ensure_quick_workspace)
    monkeypatch.setattr("sancho.cli_mcp_commands.write_client_config", fake_write_client_config)

    assert (
        main(
            [
                "mcp",
                "config",
                "--client",
                "claude-desktop",
                "--quick",
                "--profile",
                "lean",
                "--modules",
                "world_bank,pack.us_housing",
                "--quick-home",
                str(quick_home),
                "--sync",
            ]
        )
        == 0
    )

    ensure_kwargs = calls["ensure"]
    assert ensure_kwargs["profile"] == "lean"
    assert ensure_kwargs["modules_csv"] == "world_bank,pack.us_housing"
    assert ensure_kwargs["sync"] is False
    assert ensure_kwargs["install_targets"] is False

    write_kwargs = calls["write"]
    assert write_kwargs["quick"] is True
    assert write_kwargs["profile"] == "lean"
    assert write_kwargs["modules_csv"] == "world_bank,pack.us_housing"
    assert write_kwargs["sync"] is True
    assert write_kwargs["workspace_root"] == state.workspace_root
    assert write_kwargs["quick_home"] == quick_home.resolve()
