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


def test_mode_json_returns_only_developer_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SANCHO_DEVELOPER_MODE", raising=False)
    workspace = _init_workspace(tmp_path)
    secret = "secret-value-that-must-not-leak"
    (workspace / ".env").write_text(
        f"FRED_API_KEY={secret}\nSANCHO_DEVELOPER_MODE=true\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = main(["mode", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output) == {"developer_mode": True}


def test_mode_defaults_false_without_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SANCHO_DEVELOPER_MODE", raising=False)
    monkeypatch.setattr("sancho.library.read_library_record", lambda: None)
    monkeypatch.setattr("sancho.cli_mode.REPO_ENV_EXAMPLE", tmp_path / "missing.env.example")
    capsys.readouterr()

    rc = main(["mode", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"developer_mode": False}
