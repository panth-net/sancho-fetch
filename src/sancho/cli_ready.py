from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from sancho.constants import WORKSPACE_DIRNAME
from sancho.library import library_config_path, library_status
from sancho.modules import resolve_module_for_execution
from sancho.workspace import find_workspace_root


def _status(ok: bool, detail: str = "") -> dict[str, Any]:
    return {"ok": ok, "detail": detail}


def _resolve_workspace(path_arg: str) -> Path | None:
    try:
        return find_workspace_root(Path(path_arg).resolve())
    except Exception:
        return None


def _skills_status() -> dict[str, Any]:
    home = Path.home()
    expected = [
        home / ".claude" / "skills" / "sancho" / "SKILL.md",
        home / ".claude" / "skills" / "sancho-update" / "SKILL.md",
        home / ".agents" / "skills" / "sancho" / "SKILL.md",
        home / ".agents" / "skills" / "sancho-update" / "SKILL.md",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    return {
        "ok": not missing,
        "expected_count": len(expected),
        "missing": missing,
    }


def _mcp_status(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {"ok": False, "missing": ["workspace missing"]}
    expected = [
        workspace / "mcp" / "claude-desktop.mcp.json",
        workspace / "mcp" / "cursor.mcp.json",
        workspace / "mcp" / "vscode.mcp.json",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    return {
        "ok": not missing,
        "expected_count": len(expected),
        "missing": missing,
    }


def _sample_module_status(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return _status(False, "workspace missing")
    try:
        module = resolve_module_for_execution(workspace, "fetch.world_bank")
    except Exception as exc:
        return _status(False, f"fetch.world_bank is not installed: {exc}")
    return _status(True, str(module.module_dir))


def ready_payload(workspace_arg: str = ".") -> dict[str, Any]:
    workspace = _resolve_workspace(workspace_arg)
    lib_status = library_status()
    cli_path = shutil.which("sancho")
    checks: dict[str, Any] = {
        "cli": _status(True, cli_path or sys.argv[0]),
        "workspace": _status(workspace is not None, str(workspace) if workspace else "missing"),
        "library_pointer": {
            "ok": bool(lib_status.record and lib_status.healthy),
            "config_path": str(library_config_path()),
            "issues": lib_status.issues,
            "record": lib_status.record.to_dict() if lib_status.record else None,
        },
        "skills": _skills_status(),
        "mcp_snippets": _mcp_status(workspace),
        "sample_module": _sample_module_status(workspace),
    }
    ready = all(bool(check.get("ok")) for check in checks.values())
    safe_retry = "sancho setup --install-claude-desktop"
    if workspace is not None:
        safe_retry = f"sancho setup --path {workspace.parent} --install-claude-desktop"
    return {
        "ready": ready,
        "workspace": str(workspace) if workspace else None,
        "checks": checks,
        "safe_retry": safe_retry,
        "user_action_required": False,
    }


def cmd_ready(args: argparse.Namespace) -> int:
    payload = ready_payload(getattr(args, "workspace", "."))
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0 if payload["ready"] else 1
    if payload["ready"]:
        print("Sancho is ready.")
        return 0
    print("Sancho is not ready yet.")
    print(f"Safe retry: {payload['safe_retry']}")
    return 1


def add_ready_subcommand(subparsers: argparse._SubParsersAction) -> None:
    ready = subparsers.add_parser(
        "ready",
        help="Verify CLI, workspace, library pointer, skills, MCP snippets, and sample module",
    )
    ready.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    ready.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    ready.set_defaults(func=cmd_ready)
