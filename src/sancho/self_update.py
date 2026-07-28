"""Version awareness and the low-noise update nudge, for both install modes.

``sancho update`` reconciles the workspace's ``source/**`` to the module
templates bundled in the *installed* package. How new code arrives depends on
``install_source``:

- ``package`` (the normal user case: ``uv tool install sancho-fetch``): the
  agent runs ``uv tool upgrade sancho-fetch``, which pulls the newest release
  from PyPI. No checkout, no Git.
- ``checkout`` (developers): the user pulls new commits and the agent
  reinstalls from the checkout with ``uv tool install --force <repo>``.

Either way the command is run by the agent, never by sancho in-process --
reinstalling in-process would fail on Windows where the running
``sancho.exe`` shim is locked.

This module detects the two situations worth exactly one plain sentence:

- the installed package is out of date (behind PyPI, or different from the
  checkout) -> ``reinstall_needed`` plus the exact command;
- upstream has a newer version -> ``update_hint``, probed at most once per
  14 days, silent on any failure, disabled with ``SANCHO_UPDATE_NUDGE=false``.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from sancho import __version__ as SANCHO_VERSION

UPSTREAM_REPO = "panth-net/sancho-fetch"
UPSTREAM_PYPROJECT_URL = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/master/pyproject.toml"
PYPI_PROJECT = "sancho-fetch"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PYPI_PROJECT}/json"
UPGRADE_COMMAND = f"uv tool upgrade {PYPI_PROJECT}"
NUDGE_INTERVAL = timedelta(days=14)
NUDGE_STAMP_NAME = "update-nudge.json"
NUDGE_ENV_KEY = "SANCHO_UPDATE_NUDGE"
_PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_FALSE_VALUES = {"0", "false", "no", "n", "off"}


def _parse_version(value: str) -> Version | None:
    try:
        return Version(str(value).strip())
    except InvalidVersion:
        return None


def _network_allowed() -> bool:
    """Central seam: probes never fire from a test run."""
    return "PYTEST_CURRENT_TEST" not in os.environ


def read_checkout_version(repo_root: Path) -> str | None:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        match = _PYPROJECT_VERSION_RE.search(pyproject.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return match.group(1) if match else None


def _checkout_root(workspace_root: Path) -> Path | None:
    candidate = workspace_root.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    try:
        from sancho.library import read_library_record

        record = read_library_record()
    except Exception:
        return None
    if record is not None and (record.primary_repo / "pyproject.toml").exists():
        return record.primary_repo
    return None


def _stamp_path(workspace_root: Path) -> Path:
    return workspace_root / "logs" / NUDGE_STAMP_NAME


def _read_stamp(workspace_root: Path) -> dict[str, Any] | None:
    try:
        return json.loads(_stamp_path(workspace_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_stamp(workspace_root: Path, source: str, upstream_version: str | None) -> None:
    stamp_path = _stamp_path(workspace_root)
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(
        json.dumps({
            "last_check": datetime.now(timezone.utc).isoformat(),
            "upstream_version": upstream_version,
            "source": source,
        }),
        encoding="utf-8",
    )


def _fetch_upstream_version(source: str) -> str | None:
    """One live probe (~2s budget). ``checkout`` reads the repo's pyproject on
    GitHub; ``package`` reads the latest release on PyPI. None on any failure."""
    import requests

    try:
        if source == "checkout":
            response = requests.get(UPSTREAM_PYPROJECT_URL, timeout=2)
            response.raise_for_status()
            match = _PYPROJECT_VERSION_RE.search(response.text)
            return match.group(1) if match else None
        response = requests.get(PYPI_JSON_URL, timeout=2)
        response.raise_for_status()
        version = response.json().get("info", {}).get("version")
        return str(version) if version else None
    except Exception:
        return None


def package_status(workspace_root: Path, *, probe: bool = False) -> dict[str, Any]:
    """Report whether the installed package is out of date, and the exact fix.

    Offline and deterministic by default. ``probe=True`` (used by the explicit
    ``sancho update check``) allows one live PyPI probe in package mode,
    stamped so ambient nudges stay quiet afterwards.
    """
    status: dict[str, Any] = {
        "installed_version": SANCHO_VERSION,
        "install_source": "package",
        "checkout_version": None,
        "checkout_path": None,
        "upstream_version": None,
        "reinstall_needed": False,
        "reinstall_command": None,
    }
    repo_root = _checkout_root(workspace_root)
    if repo_root is not None:
        checkout_version = read_checkout_version(repo_root)
        status["install_source"] = "checkout"
        status["checkout_path"] = str(repo_root)
        status["checkout_version"] = checkout_version
        # The visible folder is the source of truth: any mismatch (newer OR
        # older checkout) means the installed package should be re-aligned.
        if checkout_version and checkout_version != SANCHO_VERSION:
            status["reinstall_needed"] = True
            status["reinstall_command"] = f'uv tool install --force "{repo_root}"'
        return status

    # Package mode: the newest PyPI release is the only actionable upstream.
    upstream_version: str | None = None
    stamp = _read_stamp(workspace_root)
    if stamp is not None and stamp.get("source") == "package":
        upstream_version = stamp.get("upstream_version")
    if probe and _network_allowed():
        fetched = _fetch_upstream_version("package")
        if fetched is not None:
            upstream_version = fetched
        _write_stamp(workspace_root, "package", upstream_version)
    status["upstream_version"] = upstream_version
    upstream_parsed = _parse_version(upstream_version) if upstream_version else None
    installed_parsed = _parse_version(SANCHO_VERSION)
    if upstream_parsed and installed_parsed and upstream_parsed > installed_parsed:
        status["reinstall_needed"] = True
        status["reinstall_command"] = UPGRADE_COMMAND
    return status


def _nudge_disabled(workspace_root: Path) -> bool:
    value = os.environ.get(NUDGE_ENV_KEY)
    if value is not None:
        return value.strip().lower() in _FALSE_VALUES
    env_file = workspace_root / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith(f"{NUDGE_ENV_KEY}="):
                    return stripped.split("=", 1)[1].strip().lower() in _FALSE_VALUES
        except OSError:
            return False
    return False


def update_hint(workspace_root: Path) -> str | None:
    """One plain sentence when upstream is newer; None in every other case.

    Never raises, never blocks for more than ~2s, probes at most once per
    NUDGE_INTERVAL per workspace, and stays quiet under pytest.
    """
    if not _network_allowed():
        return None
    try:
        if _nudge_disabled(workspace_root):
            return None
        now = datetime.now(timezone.utc)
        stamp = _read_stamp(workspace_root)
        if stamp is not None:
            last_check = datetime.fromisoformat(stamp.get("last_check"))
            if now - last_check < NUDGE_INTERVAL:
                return None

        source = "checkout" if _checkout_root(workspace_root) is not None else "package"
        upstream_version = _fetch_upstream_version(source)
        # Stamp even on failure so offline machines stay quiet instead of
        # re-probing on every command.
        _write_stamp(workspace_root, source, upstream_version)

        if not upstream_version:
            return None
        local_version = (
            package_status(workspace_root).get("checkout_version") or SANCHO_VERSION
        )
        upstream_parsed = _parse_version(upstream_version)
        local_parsed = _parse_version(str(local_version))
        if upstream_parsed and local_parsed and upstream_parsed > local_parsed:
            return (
                f"Sancho {upstream_version} is available (you have {local_version}). "
                "Say 'update Sancho' when you want it."
            )
        return None
    except Exception:
        return None


__all__ = [
    "PYPI_JSON_URL",
    "PYPI_PROJECT",
    "UPGRADE_COMMAND",
    "UPSTREAM_REPO",
    "package_status",
    "read_checkout_version",
    "update_hint",
]
