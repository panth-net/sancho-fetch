from __future__ import annotations

from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import REQUIRED_DIRECTORIES, REQUIRED_FILES, WORKSPACE_DIRNAME

pytestmark = pytest.mark.e2e


def test_init_empty_folder_is_idempotent(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    workspace = tmp_path / WORKSPACE_DIRNAME
    assert workspace.exists()

    for directory in REQUIRED_DIRECTORIES:
        assert (workspace / directory).exists()
    for file_name in REQUIRED_FILES:
        assert (workspace / file_name).exists()
    assert (workspace / "source" / "_runtime" / "ANALYSIS_GUIDE.md").exists()
    assert (workspace / "source" / "_runtime" / "DASHBOARD_GUIDE.md").exists()

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert workspace.exists()


def test_init_existing_repo_isolated_subdir(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("existing repo file\n", encoding="utf-8")

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0

    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "existing repo file\n"
    assert (tmp_path / WORKSPACE_DIRNAME).exists()
