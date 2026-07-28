from __future__ import annotations

from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.modules import discover_module_map, resolve_module_for_execution


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_resolve_auto_installs_bundled_module(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    # Not installed yet -- resolving for execution must install it on the fly so
    # the agent never has to `sancho add` before `sancho run`.
    assert "fetch.world_bank" not in discover_module_map(workspace, zone="source")

    location = resolve_module_for_execution(workspace, "fetch.world_bank")

    assert location.module_dir.exists()
    assert (location.module_dir / "module.yaml").exists()
    assert "fetch.world_bank" in discover_module_map(workspace, zone="source")


def test_resolve_unknown_module_still_raises(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    with pytest.raises(KeyError):
        resolve_module_for_execution(workspace, "fetch.not_a_real_module_xyz")


def test_resolve_prefers_already_installed(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    location = resolve_module_for_execution(workspace, "fetch.world_bank")
    assert location.zone in {"source", "custom"}
