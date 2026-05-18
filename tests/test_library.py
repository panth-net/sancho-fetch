from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from sancho import library
from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.sancho to a tmp directory so tests don't touch the real one."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_register_records_repo_and_workspace(fake_home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)

    record = library.register_library(repo)

    assert record.primary_repo == repo.resolve()
    assert record.primary_workspace == (repo / WORKSPACE_DIRNAME).resolve()
    assert record.registered_at  # ISO timestamp populated
    assert library.library_config_path().exists()


def test_register_accepts_workspace_path_directly(fake_home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    workspace = _init_workspace(repo)

    record = library.register_library(workspace)

    assert record.primary_repo == repo.resolve()
    assert record.primary_workspace == workspace.resolve()


def test_register_refuses_directory_without_workspace(fake_home: Path, tmp_path: Path) -> None:
    plain = tmp_path / "not-a-sancho-folder"
    plain.mkdir()
    with pytest.raises(FileNotFoundError, match="No 'sancho-workspace' found"):
        library.register_library(plain)


def test_read_library_record_returns_none_when_missing(fake_home: Path) -> None:
    assert library.read_library_record() is None


def test_library_status_reports_missing_repo(fake_home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)
    library.register_library(repo)

    # Simulate the user moving the folder.
    moved = tmp_path / "MovedAway"
    repo.rename(moved)

    status = library.library_status()
    assert status.record is not None
    assert not status.healthy
    assert any("primary_repo missing" in issue for issue in status.issues)


def test_cli_library_show_json_when_unregistered(fake_home: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["library", "show", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"record": None, "issues": ["No library registered."]}


def test_cli_library_show_json_when_registered(fake_home: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)
    library.register_library(repo)
    capsys.readouterr()  # drain init noise

    rc = main(["library", "show", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["issues"] == []
    assert payload["record"]["primary_repo"] == str(repo.resolve())
    assert payload["record"]["primary_workspace"] == str((repo / WORKSPACE_DIRNAME).resolve())


def test_cli_library_register_persists(fake_home: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)

    rc = main(["library", "register", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Registered sancho-fetch library" in out

    record = library.read_library_record()
    assert record is not None
    assert record.primary_repo == repo.resolve()


def test_cli_library_repair_when_repo_moved(fake_home: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)
    library.register_library(repo)
    repo.rename(tmp_path / "MovedAway")

    rc = main(["library", "repair"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "sancho library register" in out


def test_cli_library_open_calls_platform_opener(
    fake_home: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    repo = tmp_path / "sancho-fetch"
    repo.mkdir()
    _init_workspace(repo)
    library.register_library(repo)

    with patch("sancho.cli_library.open_in_file_manager") as opener:
        rc = main(["library", "open"])
    assert rc == 0
    opener.assert_called_once_with(repo.resolve())


def test_cli_library_open_without_registration(fake_home: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["library", "open"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "No library registered" in err
