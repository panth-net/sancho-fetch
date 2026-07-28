"""Sancho library registration: a pointer to the user's visible sancho-fetch folder.

The library record lives at ``~/.sancho/config.yaml`` and contains only a
pointer -- never a second hidden workspace. The visible folder remains the
single source of truth; this file just lets Sancho (and Claude/Codex) find it
from any working directory.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sancho.constants import WORKSPACE_DIRNAME
from sancho.utils import read_yaml, utc_now_iso, write_yaml


def library_config_path() -> Path:
    """Return the absolute path to the user's library pointer config."""
    return (Path.home() / ".sancho" / "config.yaml").resolve()


@dataclass
class LibraryRecord:
    primary_repo: Path
    primary_workspace: Path
    registered_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "primary_repo": str(self.primary_repo),
            "primary_workspace": str(self.primary_workspace),
            "registered_at": self.registered_at,
        }


def _resolve_repo_and_workspace(input_path: Path) -> tuple[Path, Path]:
    """Given a user-supplied path, derive (primary_repo, primary_workspace).

    Accepts the sancho-fetch repo root (containing a sancho-workspace/) or the
    workspace folder itself.
    """
    resolved = input_path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    if resolved.name == WORKSPACE_DIRNAME:
        return resolved.parent, resolved

    candidate = resolved / WORKSPACE_DIRNAME
    if candidate.exists():
        return resolved, candidate

    raise FileNotFoundError(
        f"No '{WORKSPACE_DIRNAME}' found at or under {resolved}. "
        "Run 'sancho setup --path <path-to-sancho-fetch>' first or point "
        "register at your sancho-fetch folder."
    )


def register_library(input_path: Path) -> LibraryRecord:
    """Save a pointer to the visible sancho-fetch folder."""
    primary_repo, primary_workspace = _resolve_repo_and_workspace(input_path)
    record = LibraryRecord(
        primary_repo=primary_repo,
        primary_workspace=primary_workspace,
        registered_at=utc_now_iso(),
    )
    write_yaml(library_config_path(), record.to_dict())
    return record


def read_library_record() -> LibraryRecord | None:
    """Load the registered library pointer, or None if not registered."""
    cfg = library_config_path()
    if not cfg.exists():
        return None
    payload = read_yaml(cfg) or {}
    if not isinstance(payload, dict):
        return None
    repo = payload.get("primary_repo")
    workspace = payload.get("primary_workspace")
    if not isinstance(repo, str) or not isinstance(workspace, str):
        return None
    registered_at = payload.get("registered_at") or ""
    return LibraryRecord(
        primary_repo=Path(repo),
        primary_workspace=Path(workspace),
        registered_at=str(registered_at),
    )


@dataclass
class LibraryStatus:
    record: LibraryRecord | None
    issues: list[str]

    @property
    def healthy(self) -> bool:
        return self.record is not None and not self.issues


def library_status() -> LibraryStatus:
    """Inspect the registered library and report what is missing or moved."""
    record = read_library_record()
    if record is None:
        return LibraryStatus(record=None, issues=["No library registered."])
    issues: list[str] = []
    if not record.primary_repo.exists():
        issues.append(f"primary_repo missing: {record.primary_repo}")
    if not record.primary_workspace.exists():
        issues.append(f"primary_workspace missing: {record.primary_workspace}")
    return LibraryStatus(record=record, issues=issues)


def open_in_file_manager(path: Path) -> None:
    """Reveal a folder in the user's file manager. Best-effort, non-blocking."""
    target = str(path)
    system = platform.system()
    if system == "Windows" and hasattr(os, "startfile"):
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if system == "Darwin":
        subprocess.run(["open", target], check=False)
        return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.run([opener, target], check=False)
        return
    raise RuntimeError(f"No file-manager opener available for platform '{system}'")


def git_status_summary(repo_root: Path) -> dict[str, Any] | None:
    """Return a short git status summary, or None if the repo isn't a git work tree."""
    if not (repo_root / ".git").exists():
        return None
    git = shutil.which("git")
    if not git:
        return None
    try:
        result = subprocess.run(
            [git, "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    modified = sum(1 for line in lines if line[:2].strip())
    return {"is_git_repo": True, "changed_files": modified, "clean": modified == 0}
