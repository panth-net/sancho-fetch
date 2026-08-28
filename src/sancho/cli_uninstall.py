"""Data-preserving uninstall and explicitly targeted workspace purge."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.client_integrations import LaunchDefinition, client_adapters
from sancho.constants import WORKSPACE_DIRNAME
from sancho.install_state import (
    WORKSPACE_SCHEMA_MAX_READER,
    WORKSPACE_SCHEMA_MIN_READER,
    InstallStateError,
    install_state_path,
    load_install_state,
    locks_root,
    read_workspace_identity,
    save_install_state,
    state_lock,
)
from sancho.utils import file_sha256


def _launch_from_state(state: dict[str, Any]) -> LaunchDefinition:
    # Client removal uses each adapter's recorded installed value. These
    # fallback launch fields avoid requiring a still-present workspace — or
    # even a workspace record at all (it is cleared by --purge-workspace) —
    # merely to detach a stale registration.
    workspace = state.get("workspace")
    workspace_path = ""
    workspace_id = ""
    if isinstance(workspace, dict):
        workspace_path = str(workspace.get("resolved_path") or "")
        workspace_id = str(workspace.get("workspace_id") or "")
    executable = "sancho"
    arguments = (
        "mcp",
        "serve",
        *(("--workspace", workspace_path) if workspace_path else ()),
        "--transport",
        "stdio",
    )
    for record in state.get("clients", {}).values():
        if not isinstance(record, dict):
            continue
        installed = record.get("installed_value")
        if isinstance(installed, dict) and isinstance(installed.get("command"), str):
            executable = installed["command"]
            arguments = tuple(str(value) for value in installed.get("args", arguments))
            break
    return LaunchDefinition(
        server_name="sancho",
        executable=executable,
        arguments=arguments,
        transport="stdio",
        environment={},
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        workspace_selection="recorded-workspace",
        package_version=str(state.get("package_version") or SANCHO_VERSION),
        workspace_schema_min=WORKSPACE_SCHEMA_MIN_READER,
        workspace_schema_max=WORKSPACE_SCHEMA_MAX_READER,
    )


def _record(bucket: list[dict[str, Any]], *, kind: str, path: Path | None = None, detail: str = "") -> None:
    item: dict[str, Any] = {"kind": kind, "detail": detail}
    if path is not None:
        item["path"] = str(path)
    bucket.append(item)


def _remove_owned_files(state: dict[str, Any], payload: dict[str, Any]) -> None:
    owned = state.get("owned_files", {})
    for raw_path, record in list(owned.items()):
        if not isinstance(record, dict):
            _record(payload["failed"], kind="owned-file-record", path=Path(raw_path), detail="invalid ownership entry")
            continue
        path = Path(raw_path)
        if not path.exists():
            owned.pop(raw_path, None)
            _record(payload["removed"], kind=str(record.get("kind", "file")), path=path, detail="already absent")
            continue
        try:
            current = file_sha256(path)
        except OSError as exc:
            _record(payload["failed"], kind=str(record.get("kind", "file")), path=path, detail=str(exc))
            continue
        if current != record.get("sha256"):
            _record(payload["drifted"], kind=str(record.get("kind", "file")), path=path, detail="current bytes differ; preserved")
            continue
        try:
            path.unlink()
        except OSError as exc:
            _record(payload["failed"], kind=str(record.get("kind", "file")), path=path, detail=str(exc))
            continue
        owned.pop(raw_path, None)
        _record(payload["removed"], kind=str(record.get("kind", "file")), path=path, detail="matching Sancho-owned file removed")
        try:
            # Tidy the now-empty container (e.g. ~/.claude/skills/sancho/).
            # rmdir refuses non-empty directories, so user content is safe.
            path.parent.rmdir()
        except OSError:
            pass


def _default_uninstall() -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {
        "status": "ok",
        "removed": [],
        "preserved": [],
        "drifted": [],
        "user_action_required": [],
        "failed": [],
        "workspaces_removed": [],
        "package_uninstall_command": "uv tool uninstall sancho-fetch",
    }
    if not install_state_path().exists():
        # Nothing was ever set up (or it was already uninstalled): that is a
        # clean no-op, not an error. A present-but-corrupt record still fails
        # closed below.
        _record(
            payload["preserved"],
            kind="ownership-state",
            detail="no Sancho installation state on this machine; nothing to remove",
        )
        return payload, 0
    try:
        state = load_install_state(allow_missing=False)
        launch = _launch_from_state(state)
    except InstallStateError as exc:
        payload["status"] = "failed"
        _record(payload["failed"], kind="ownership-state", detail=str(exc))
        payload["user_action_required"].append(
            {"kind": "ownership-state", "detail": "Restore the ownership record; no shared state was removed."}
        )
        return payload, 1

    vscode_record = state["clients"].get("vscode")
    vscode_path = None
    if isinstance(vscode_record, dict) and vscode_record.get("config_path"):
        vscode_path = Path(str(vscode_record["config_path"]))
    adapters = client_adapters(launch, vscode_config_path=vscode_path)
    for name in list(state["clients"]):
        adapter = adapters.get(name)
        if adapter is None:
            _record(payload["failed"], kind="client", detail=f"no adapter for recorded client {name}")
            continue
        result = adapter.remove(launch)
        if result.state in {"removed", "unchanged"}:
            target = payload["removed"]
        elif result.state == "preserved_drift":
            target = payload["drifted"]
        elif result.state in {"user_action_required", "policy_blocked"}:
            target = payload["user_action_required"]
        else:
            target = payload["failed"]
        target.append({"kind": "client", **result.to_dict()})

    # Reload after adapters record their successful removals, then compare and
    # remove owned skill/pointer files byte-for-byte.
    try:
        with state_lock():
            state = load_install_state(allow_missing=False)
            _remove_owned_files(state, payload)
            save_install_state(state)
    except InstallStateError as exc:
        _record(payload["failed"], kind="ownership-state", detail=str(exc))

    workspace_records: list[dict[str, Any]] = []
    current = state.get("workspace")
    if isinstance(current, dict):
        workspace_records.append(current)
    workspace_records.extend(item for item in state.get("workspace_history", []) if isinstance(item, dict))
    for record in workspace_records:
        path = Path(str(record.get("resolved_path", "")))
        if path and path.exists():
            _record(
                payload["preserved"],
                kind="data-bearing-workspace",
                path=path,
                detail=f"preserved workspace ID {record.get('workspace_id')}",
            )
    quick_root = Path.home() / ".sancho" / "mcp-quick"
    if quick_root.exists():
        _record(payload["preserved"], kind="quick-workspace-root", path=quick_root, detail="preserved by default")

    if not payload["failed"] and not payload["drifted"] and not payload["user_action_required"]:
        try:
            install_state_path().unlink(missing_ok=True)
            _record(payload["removed"], kind="ownership-state", path=install_state_path(), detail="control record removed")
        except OSError as exc:
            _record(payload["failed"], kind="ownership-state", path=install_state_path(), detail=str(exc))
        # Lock files are ephemeral control state; leave nothing behind.
        shutil.rmtree(locks_root(), ignore_errors=True)
    else:
        payload["user_action_required"].append(
            {"kind": "preserved-state", "detail": "Ownership state was kept so drift/failures can be repaired later."}
        )
    if payload["failed"]:
        payload["status"] = "failed"
    elif payload["drifted"] or payload["user_action_required"]:
        payload["status"] = "user_action_required"
    return payload, 1 if payload["failed"] else 0


def _unsafe_purge_reason(path: Path) -> str | None:
    if path.is_symlink():
        return "symlink workspace targets are not accepted for purge"
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        return "refusing a root or home directory"
    if resolved.name != WORKSPACE_DIRNAME:
        return f"target must be the exact {WORKSPACE_DIRNAME} directory"
    if len(resolved.parts) < 3:
        return "target is too broad"
    return None


def _resolve_downloads_target(raw: str | None) -> tuple[Path | None, str | None]:
    if not raw:
        return None, None
    path = Path(raw).expanduser()
    if path.is_symlink():
        return None, "downloads target may not be a symlink"
    resolved = path.resolve()
    if resolved.name != "sancho-downloads" or resolved == Path.home().resolve():
        return None, "downloads target must be one exact non-home sancho-downloads folder"
    if len(resolved.parts) < 3:
        return None, "downloads target is too broad"
    return resolved, None


def _purge_downloads_only(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {
        "status": "failed",
        "removed": [],
        "preserved": [],
        "drifted": [],
        "user_action_required": [],
        "failed": [],
        "workspaces_removed": [],
    }
    downloads, reason = _resolve_downloads_target(args.purge_downloads)
    if reason or downloads is None:
        _record(payload["failed"], kind="downloads", detail=reason or "downloads target missing")
        return payload, 1
    if not args.yes:
        answer = input(f"Permanently delete downloads at {downloads}? Type DELETE to confirm: ").strip()
        if answer != "DELETE":
            payload["status"] = "canceled"
            _record(payload["preserved"], kind="downloads", path=downloads, detail="confirmation did not match")
            return payload, 0
    if downloads.exists():
        try:
            shutil.rmtree(downloads)
        except OSError as exc:
            _record(payload["failed"], kind="downloads", path=downloads, detail=str(exc))
            return payload, 1
        _record(payload["removed"], kind="downloads", path=downloads, detail="explicitly purged")
    else:
        _record(payload["removed"], kind="downloads", path=downloads, detail="already absent")
    payload["status"] = "ok"
    return payload, 0


def _purge(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {
        "status": "failed",
        "removed": [],
        "preserved": [],
        "drifted": [],
        "user_action_required": [],
        "failed": [],
        "workspaces_removed": [],
    }
    if not args.workspace_id:
        _record(payload["failed"], kind="purge", detail="--workspace-id is required")
        return payload, 1
    raw_target = Path(args.workspace).expanduser() if args.workspace else None
    if raw_target is None:
        try:
            state = load_install_state(allow_missing=False)
            active = state.get("workspace")
            history = [active, *state.get("workspace_history", [])]
            matches = [
                item for item in history
                if isinstance(item, dict) and item.get("workspace_id") == args.workspace_id
            ]
        except InstallStateError as exc:
            _record(payload["failed"], kind="purge", detail=str(exc))
            return payload, 1
        if len(matches) != 1:
            _record(payload["failed"], kind="purge", detail="workspace target is ambiguous; pass --workspace")
            return payload, 1
        raw_target = Path(str(matches[0]["resolved_path"]))
    reason = _unsafe_purge_reason(raw_target)
    if reason:
        _record(payload["failed"], kind="purge", path=raw_target, detail=reason)
        return payload, 1
    target = raw_target.resolve()
    try:
        identity = read_workspace_identity(target)
    except InstallStateError as exc:
        _record(payload["failed"], kind="purge", path=target, detail=str(exc))
        return payload, 1
    if identity["workspace_id"] != args.workspace_id:
        _record(payload["failed"], kind="purge", path=target, detail="workspace ID does not match target")
        return payload, 1
    downloads, downloads_reason = _resolve_downloads_target(args.purge_downloads)
    if downloads_reason:
        _record(payload["failed"], kind="downloads", detail=downloads_reason)
        return payload, 1
    if install_state_path().exists():
        try:
            load_install_state(allow_missing=False)
        except InstallStateError as exc:
            _record(payload["failed"], kind="ownership-state", detail=str(exc))
            return payload, 1
    if not args.yes:
        answer = input(
            f"Permanently delete workspace {identity['workspace_id']} at {target}? Type the workspace ID to confirm: "
        ).strip()
        if answer != args.workspace_id:
            payload["status"] = "canceled"
            _record(payload["preserved"], kind="data-bearing-workspace", path=target, detail="confirmation did not match")
            return payload, 0
    try:
        shutil.rmtree(target)
        _record(payload["removed"], kind="data-bearing-workspace", path=target, detail="explicitly purged")
        payload["workspaces_removed"].append(str(target))
    except OSError as exc:
        _record(payload["failed"], kind="purge", path=target, detail=str(exc))
        return payload, 1
    if downloads is not None and downloads.exists():
        try:
            shutil.rmtree(downloads)
        except OSError as exc:
            _record(payload["failed"], kind="downloads", path=downloads, detail=str(exc))
            return payload, 1
        _record(payload["removed"], kind="downloads", path=downloads, detail="explicitly purged")
    # Forget only the exact deleted workspace identity; retain sibling history
    # and every other control record.
    if install_state_path().exists():
        try:
            with state_lock():
                state = load_install_state(allow_missing=False)
                current = state.get("workspace")
                if isinstance(current, dict) and current.get("workspace_id") == args.workspace_id:
                    state["workspace"] = None
                state["workspace_history"] = [
                    item
                    for item in state.get("workspace_history", [])
                    if not isinstance(item, dict) or item.get("workspace_id") != args.workspace_id
                ]
                save_install_state(state)
        except InstallStateError as exc:
            _record(payload["failed"], kind="ownership-state", detail=str(exc))
            return payload, 1
    payload["status"] = "ok"
    return payload, 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    if args.purge_workspace:
        payload, code = _purge(args)
    elif args.purge_downloads:
        payload, code = _purge_downloads_only(args)
    else:
        payload, code = _default_uninstall()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return code
    print(f"Sancho uninstall: {payload['status']}")
    for item in payload.get("removed", []):
        print(f"- Removed: {item.get('path') or item.get('client') or item.get('kind')}")
    for item in payload.get("preserved", []):
        print(f"- Preserved: {item.get('path') or item.get('kind')}")
    for item in payload.get("drifted", []):
        print(f"- Preserved edited item: {item.get('path') or item.get('client')}")
    for item in payload.get("failed", []):
        print(f"- Failed safely: {item.get('detail')}")
    if args.purge_downloads and not args.purge_workspace:
        print("All data-bearing workspaces were preserved.")
    elif not args.purge_workspace:
        print("All data-bearing workspaces and downloads were preserved.")
        # Must remain the final instruction: the running command never removes itself.
        print("To remove the CLI, run: uv tool uninstall sancho-fetch")
    return code


def add_uninstall_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("uninstall", help="Remove owned integrations while preserving all data by default")
    parser.add_argument("--purge-workspace", action="store_true", help="Explicitly delete one exact data workspace")
    parser.add_argument("--workspace", help="Exact sancho-workspace path for purge")
    parser.add_argument("--workspace-id", help="Exact persistent workspace ID required for purge")
    parser.add_argument("--purge-downloads", metavar="PATH", help="Separately purge one exact sancho-downloads folder")
    parser.add_argument("--yes", action="store_true", help="Skip interactive purge confirmation after all exact checks")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.set_defaults(func=cmd_uninstall)
