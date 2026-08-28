"""Durable ownership and workspace identity for installation lifecycle commands.

The state in this module is control metadata only.  User data remains in a
visible (or explicitly selected quick/extension) workspace and is never made a
child of this control directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sancho import __version__ as SANCHO_VERSION
from sancho.utils import utc_now_iso

INSTALL_STATE_SCHEMA_VERSION = 1
WORKSPACE_IDENTITY_SCHEMA_VERSION = 1
WORKSPACE_SCHEMA_VERSION = 1
WORKSPACE_SCHEMA_MIN_READER = 1
WORKSPACE_SCHEMA_MAX_READER = 1
WORKSPACE_IDENTITY_FILE = ".sancho-workspace.json"


class InstallStateError(RuntimeError):
    """State cannot be trusted, so a shared-state mutation must stop."""


def control_root() -> Path:
    return Path.home() / ".sancho" / "state"


def install_state_path() -> Path:
    return control_root() / "install-state.json"


def workspace_lifecycle_lock_path(workspace_root: Path) -> Path:
    """Return one stable control-state lock key for a resolved workspace."""
    digest = hashlib.sha256(str(workspace_root.resolve()).encode("utf-8")).hexdigest()
    return control_root() / "workspace-locks" / digest


def locks_root() -> Path:
    return control_root() / "locks"


def _lock_file_for(target: Path) -> Path:
    """Map any lock target to one file inside the central locks directory.

    Locks must never be created beside the guarded file: that would litter
    ``.lock`` files inside user-visible workspaces and other apps' config
    folders, and they would survive uninstall.
    """
    digest = hashlib.sha256(str(target.resolve()).encode("utf-8")).hexdigest()
    return locks_root() / f"{digest}.lock"


def atomic_write_json(path: Path, payload: dict[str, Any], *, sort_keys: bool = True) -> None:
    """Atomically replace ``path`` with pretty-printed JSON.

    ``sort_keys=False`` preserves insertion order for user-facing client
    configuration files; Sancho's own state records stay sorted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=sort_keys)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@contextmanager
def state_lock(path: Path | None = None, *, timeout: float = 10.0) -> Iterator[None]:
    """Take a portable advisory lock for a state or shared-config file."""
    target = _lock_file_for(path or install_state_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = target.open("a+b")
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    if target.stat().st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise InstallStateError(f"Timed out waiting for installation lock: {target}")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _new_state() -> dict[str, Any]:
    return {
        "schema_version": INSTALL_STATE_SCHEMA_VERSION,
        "revision": 0,
        "package_version": SANCHO_VERSION,
        "workspace": None,
        "workspace_history": [],
        "owned_files": {},
        "clients": {},
        "updated_at": utc_now_iso(),
    }


def load_install_state(*, allow_missing: bool = True) -> dict[str, Any]:
    path = install_state_path()
    if not path.exists():
        if allow_missing:
            return _new_state()
        raise InstallStateError(f"Installation ownership record is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallStateError(
            f"Installation ownership record is unreadable or corrupt: {path}. "
            "No shared configuration was changed."
        ) from exc
    if not isinstance(payload, dict):
        raise InstallStateError(f"Installation ownership record must be a JSON object: {path}")
    if payload.get("schema_version") != INSTALL_STATE_SCHEMA_VERSION:
        raise InstallStateError(
            f"Unsupported installation ownership schema in {path}: "
            f"{payload.get('schema_version')!r}"
        )
    for key, expected in (("owned_files", dict), ("clients", dict), ("workspace_history", list)):
        if not isinstance(payload.get(key), expected):
            raise InstallStateError(f"Invalid {key!r} field in installation ownership record: {path}")
    return payload


def save_install_state(payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["schema_version"] = INSTALL_STATE_SCHEMA_VERSION
    payload["revision"] = int(payload.get("revision", 0)) + 1
    payload["package_version"] = SANCHO_VERSION
    payload["updated_at"] = utc_now_iso()
    try:
        atomic_write_json(install_state_path(), payload)
    except OSError as exc:
        raise InstallStateError(
            f"Could not atomically write installation ownership record: {install_state_path()}"
        ) from exc


def workspace_identity_path(workspace_root: Path) -> Path:
    return workspace_root.resolve() / WORKSPACE_IDENTITY_FILE


def read_workspace_identity(workspace_root: Path) -> dict[str, Any]:
    path = workspace_identity_path(workspace_root)
    if not path.exists():
        raise InstallStateError(f"Workspace identity is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallStateError(f"Workspace identity is unreadable or corrupt: {path}") from exc
    if not isinstance(payload, dict) or payload.get("identity_schema_version") != WORKSPACE_IDENTITY_SCHEMA_VERSION:
        raise InstallStateError(f"Unsupported workspace identity schema: {path}")
    try:
        uuid.UUID(str(payload["workspace_id"]))
        schema_version = int(payload["workspace_schema_version"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InstallStateError(f"Invalid workspace identity: {path}") from exc
    if not WORKSPACE_SCHEMA_MIN_READER <= schema_version <= WORKSPACE_SCHEMA_MAX_READER:
        raise InstallStateError(
            f"Workspace schema {schema_version} is not supported by Sancho {SANCHO_VERSION}; "
            f"supported range is {WORKSPACE_SCHEMA_MIN_READER}-{WORKSPACE_SCHEMA_MAX_READER}."
        )
    resolved = str(workspace_root.resolve())
    payload["resolved_path"] = resolved
    return payload


def ensure_workspace_identity(workspace_root: Path) -> dict[str, Any]:
    path = workspace_identity_path(workspace_root)
    if path.exists():
        return read_workspace_identity(workspace_root)
    payload: dict[str, Any] = {
        "identity_schema_version": WORKSPACE_IDENTITY_SCHEMA_VERSION,
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "workspace_id": str(uuid.uuid4()),
        "created_at": utc_now_iso(),
        "created_by_version": SANCHO_VERSION,
    }
    with state_lock(path):
        if path.exists():
            return read_workspace_identity(workspace_root)
        try:
            atomic_write_json(path, payload)
        except OSError as exc:
            raise InstallStateError(f"Could not write workspace identity: {path}") from exc
    return read_workspace_identity(workspace_root)


def bind_workspace(state: dict[str, Any], workspace_root: Path, identity: dict[str, Any]) -> None:
    current = state.get("workspace")
    next_workspace = {
        "workspace_id": identity["workspace_id"],
        "resolved_path": str(workspace_root.resolve()),
        "workspace_schema_version": identity["workspace_schema_version"],
    }
    if isinstance(current, dict) and current != next_workspace:
        history = state.setdefault("workspace_history", [])
        if current not in history:
            history.append(current)
    state["workspace"] = next_workspace
