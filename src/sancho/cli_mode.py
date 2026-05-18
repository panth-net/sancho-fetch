from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sancho.constants import WORKSPACE_DIRNAME

TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off", ""}
MODE_KEY = "SANCHO_DEVELOPER_MODE"
REPO_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


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
    candidates.extend([cwd / ".env", cwd / ".env.example", REPO_ENV_EXAMPLE])

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


def cmd_mode(args: argparse.Namespace) -> int:
    payload = {"developer_mode": developer_mode(getattr(args, "workspace", "."))}
    if getattr(args, "json", False):
        print(json.dumps(payload))
        return 0
    print("Developer mode: " + ("on" if payload["developer_mode"] else "off"))
    return 0


def add_mode_subcommand(subparsers: argparse._SubParsersAction) -> None:
    mode = subparsers.add_parser(
        "mode",
        help="Report Sancho operator mode without exposing .env contents",
    )
    mode.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    mode.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    mode.set_defaults(func=cmd_mode)
