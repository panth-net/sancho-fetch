from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from sancho.client_integrations import canonical_launch_definition, client_adapters
from sancho.constants import WORKSPACE_DIRNAME
from sancho.install_state import InstallStateError, load_install_state, read_workspace_identity
from sancho.library import library_config_path, library_status
from sancho.modules import discover_modules
from sancho.self_update import update_hint
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
        workspace / "mcp" / "chatgpt-desktop.mcp.json",
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
    # Read-only lookup on purpose: ready diagnoses and must never install.
    # resolve_module_for_execution would auto-install the module from the
    # bundled templates, silently repairing the very state being checked.
    # strict=False so one broken hand-edited custom module can't mask an
    # intact sample module.
    try:
        for zone in ("custom", "source"):
            for module in discover_modules(workspace, zone=zone, strict=False):
                if module.id == "fetch.world_bank":
                    return _status(True, str(module.module_dir))
    except Exception as exc:
        return _status(False, f"could not inspect modules: {exc}")
    return _status(
        False,
        "fetch.world_bank is not installed; run `sancho setup` to restore it",
    )


def _ownership_status(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return _status(False, "workspace missing")
    try:
        identity = read_workspace_identity(workspace)
        state = load_install_state(allow_missing=False)
    except InstallStateError as exc:
        return _status(False, str(exc))
    bound = state.get("workspace")
    ok = bool(
        isinstance(bound, dict)
        and bound.get("workspace_id") == identity.get("workspace_id")
        and Path(str(bound.get("resolved_path", ""))).resolve() == workspace.resolve()
    )
    return {
        "ok": ok,
        "workspace_id": identity["workspace_id"],
        "workspace_schema_version": identity["workspace_schema_version"],
        "detail": "ownership record matches" if ok else "ownership record references another workspace/path",
    }


def _clients_status(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return _status(False, "workspace missing")
    try:
        launch = canonical_launch_definition(workspace)
        state = load_install_state(allow_missing=False)
        vscode_record = state["clients"].get("vscode")
        vscode_path = None
        if isinstance(vscode_record, dict) and vscode_record.get("config_path"):
            vscode_path = Path(str(vscode_record["config_path"]))
        adapters = client_adapters(launch, vscode_config_path=vscode_path)
    except InstallStateError as exc:
        return _status(False, str(exc))
    results: list[dict[str, Any]] = []
    for name in sorted(state["clients"]):
        adapter = adapters.get(name)
        if adapter is None:
            results.append(
                {
                    "client": name,
                    "state": "failed",
                    "detail": "recorded adapter is no longer supported",
                    "user_action_required": True,
                }
            )
            continue
        results.append(adapter.status(launch).to_dict())
    failed_states = {"failed", "preserved_drift", "user_action_required", "policy_blocked"}
    ok = all(item["state"] not in failed_states for item in results)
    return {
        "ok": ok,
        "requested_count": len(results),
        "results": results,
        "user_action_required": any(item.get("user_action_required") for item in results),
        "detail": "recorded client registrations match" if ok else "one or more recorded client registrations need attention",
    }


def ready_payload(workspace_arg: str = ".", *, require_sample_module: bool = True) -> dict[str, Any]:
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
            **(
                {
                    "hint": (
                        "The sancho-fetch folder is no longer where it was registered "
                        "(it was probably moved or renamed). Run `sancho setup --path "
                        "<current sancho-fetch folder> --switch-workspace` once "
                        "to re-register the library and safely update owned client connections."
                    )
                }
                if lib_status.record and not lib_status.healthy
                else {}
            ),
        },
        "ownership": _ownership_status(workspace),
        "skills": _skills_status(),
        "mcp_snippets": _mcp_status(workspace),
        "clients": _clients_status(workspace),
        "sample_module": _sample_module_status(workspace),
    }
    required_names = set(checks)
    if not require_sample_module:
        required_names.discard("sample_module")
        checks["sample_module"]["required"] = False
    ready = all(bool(checks[name].get("ok")) for name in required_names)
    safe_retry = "sancho setup"
    if workspace is not None:
        safe_retry = f"sancho setup --path {workspace.parent}"
    payload: dict[str, Any] = {
        "ready": ready,
        "workspace": str(workspace) if workspace else None,
        "checks": checks,
        "safe_retry": safe_retry,
        "user_action_required": any(
            bool(check.get("user_action_required")) for check in checks.values()
        ),
    }
    if workspace is not None:
        hint = update_hint(workspace)
        if hint:
            payload["update_hint"] = hint
    return payload


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
