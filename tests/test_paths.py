from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho import library
from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _init_workspace(repo: Path) -> Path:
    rc = main(["init", "--path", str(repo), "--yes"])
    assert rc == 0
    return repo / WORKSPACE_DIRNAME


def test_paths_json_resolves_via_cwd_when_inside_repo(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    workspace = _init_workspace(repo)
    monkeypatch.chdir(repo)
    capsys.readouterr()  # drain init noise

    rc = main(["paths", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["workspace_source"] == "cwd"
    assert payload["workspace"]["workspace"] == str(workspace)
    assert payload["workspace"]["fetched_data"] == str(workspace / "fetched-data")
    assert payload["workspace"]["logs"] == str(workspace / "logs")
    assert payload["workspace"]["env_file"] == str(workspace / ".env")
    assert payload["library"]["registered"] is False
    assert payload["project_copy_target"].endswith("sancho-fetched-data")


def test_paths_uses_registered_library_when_cwd_unrelated(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    workspace = _init_workspace(repo)
    library.register_library(repo)

    elsewhere = tmp_path / "Some Project"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    capsys.readouterr()  # drain init noise

    rc = main(["paths", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["workspace_source"] == "library"
    assert payload["workspace"]["workspace"] == str(workspace)
    assert payload["current_project"] == str(elsewhere.resolve())
    assert payload["project_copy_target"] == str(elsewhere.resolve() / "sancho-fetched-data")
    assert payload["library"]["registered"] is True


def test_paths_returns_failure_when_no_workspace(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    elsewhere = tmp_path / "Nowhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    rc = main(["paths"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "no workspace found" in out
    assert "sancho setup --install-claude-desktop" in out


def test_paths_human_output_includes_core_labels(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)
    monkeypatch.chdir(repo)

    rc = main(["paths"])
    assert rc == 0
    out = capsys.readouterr().out
    for label in ("Root:", "Workspace:", "Source modules:", "Custom modules:",
                   "Fetched data:", "Logs:", "Env file:"):
        assert label in out
