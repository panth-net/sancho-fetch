from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_module_show_returns_manifest_and_paths(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["module", "show", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["module_id"] == "fetch.world_bank"
    assert payload["type"] == "fetch"
    assert payload["entrypoint"]
    assert payload["custom_override_active"] is False
    assert payload["source_path"]
    assert payload["template_path"]


def test_module_files_lists_installed_files(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["module", "files", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["zone"] == "source"
    assert "module.yaml" in payload["files"]


def test_module_status_reports_in_source(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["module", "status", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["installed"] is True
    assert payload["in_source"] is True
    assert payload["in_custom"] is False
    assert payload["custom_override_active"] is False


def test_module_show_reflects_custom_override(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Create a custom override.
    custom = workspace / "custom" / "fetch" / "fetch_world_bank"
    custom.mkdir(parents=True)
    (custom / "module.yaml").write_text(
        "id: fetch.world_bank\nversion: 9.9.9\ntype: fetch\nentrypoint: main.py:run\ncatalog_tier: large\nmanaged_paths:\n  - module.yaml\n",
        encoding="utf-8",
    )
    (custom / "main.py").write_text("def run(context, payload): return {}\n", encoding="utf-8")
    capsys.readouterr()
    rc = main(["module", "show", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["custom_override_active"] is True
    assert payload["custom_path"]


def test_module_docs_returns_existing_files(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["module", "docs", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["module_id"] == "fetch.world_bank"
    assert any(section.get("module_yaml") for section in payload["docs"].values())
