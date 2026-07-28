from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sancho.constants import BUNDLED_ENV_EXAMPLE as _BUNDLED_ENV_EXAMPLE
from sancho.constants import WORKSPACE_DIRNAME

TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off", ""}
MODE_KEY = "SANCHO_DEVELOPER_MODE"
# Module-level binding (not a bare re-export) so tests can monkeypatch it.
BUNDLED_ENV_EXAMPLE = _BUNDLED_ENV_EXAMPLE


def _parse_bool(value: str) -> bool:
    normalized = value.split("#", 1)[0].strip().strip('"').strip("'").lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return False


def _read_mode_from_file(path: Path) -> bool | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                if stripped.startswith("export "):
                    stripped = stripped[len("export ") :].lstrip()
                name, value = stripped.split("=", 1)
                if name.strip() == MODE_KEY:
                    return _parse_bool(value)
    except OSError:
        return None
    return None


def _workspace_from_arg(path_arg: str) -> Path | None:
    path = Path(path_arg).resolve()
    if path.name == WORKSPACE_DIRNAME and path.exists():
        return path
    candidate = path / WORKSPACE_DIRNAME
    if candidate.exists():
        return candidate
    try:
        from sancho.library import read_library_record

        record = read_library_record()
    except Exception:
        return None
    if record is not None and record.primary_workspace.exists():
        return record.primary_workspace
    return None


def developer_mode(workspace_arg: str = ".") -> bool:
    env_value = os.environ.get(MODE_KEY)
    if env_value is not None:
        return _parse_bool(env_value)

    workspace = _workspace_from_arg(workspace_arg)
    candidates: list[Path] = []
    if workspace is not None:
        candidates.extend([workspace / ".env", workspace / ".env.example"])

    cwd = Path(workspace_arg).resolve()
    candidates.extend([cwd / ".env", cwd / ".env.example", BUNDLED_ENV_EXAMPLE])

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        value = _read_mode_from_file(resolved)
        if value is not None:
            return value
    return False


def _write_mode_to_file(path: Path, value: bool) -> None:
    """Set MODE_KEY in a KEY=value file, leaving every other line untouched."""
    rendered = f"{MODE_KEY}={'true' if value else 'false'}\n"
    lines: list[str] = []
    replaced = False
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].lstrip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.split("=", 1)[0].strip() == MODE_KEY:
                lines[index] = rendered
                replaced = True
                break
    if not replaced:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(rendered)
    _atomic_write_text(path, "".join(lines))


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename over the target.

    This file holds the user's API keys. A crash or full disk partway through a
    plain write would truncate it; os.replace is atomic on POSIX and Windows,
    so the file is either the old contents or the new one, never half of each.
    """
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def cmd_mode(args: argparse.Namespace) -> int:
    workspace_arg = getattr(args, "workspace", ".")
    set_value = getattr(args, "set_value", None)
    payload: dict[str, object] = {}
    if set_value is not None:
        workspace = _workspace_from_arg(workspace_arg)
        if workspace is None:
            message = (
                "No sancho-workspace found, so there is no .env to update. "
                "Run `sancho setup` first, or pass --workspace."
            )
            if getattr(args, "json", False):
                print(json.dumps({"error_message": message, "user_action_required": True}))
            else:
                print("ERROR: " + message)
            return 1
        env_path = workspace / ".env"
        _write_mode_to_file(env_path, set_value == "on")
        # A process-level env var would shadow the file we just wrote; surface it.
        if os.environ.get(MODE_KEY) is not None:
            payload["shadowed_by_process_env"] = True
        payload["updated"] = True
        payload["env_path"] = str(env_path)
    payload["developer_mode"] = developer_mode(workspace_arg)
    if getattr(args, "json", False):
        print(json.dumps(payload))
        return 0
    print("Developer mode: " + ("on" if payload["developer_mode"] else "off"))
    return 0


def add_mode_subcommand(subparsers: argparse._SubParsersAction) -> None:
    mode = subparsers.add_parser(
        "mode",
        help="Report or set Sancho operator mode without exposing .env contents",
    )
    mode.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    mode.add_argument(
        "--set",
        choices=["on", "off"],
        dest="set_value",
        help="Turn developer mode on or off (updates only the SANCHO_DEVELOPER_MODE line in the workspace .env)",
    )
    mode.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    mode.set_defaults(func=cmd_mode)
