"""CLI for ``sancho update check / preview / apply / rollback``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sancho.update_engine import (
    apply_updates_safe,
    check_updates,
    preview_updates_rich,
    rollback_update,
)
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def cmd_update_check(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    payload = check_updates(workspace_root)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"# Update check (sancho {payload['sancho_version']})")
    print(f"- workspace: {payload['workspace_root']}")
    print(f"- schema_version: {payload['workspace_schema_version']}")
    print(f"- modules: {payload['module_count']}  updatable: {payload['updatable_count']}")
    print(f"- env_present: {payload['env_present']}  gitignore_covers_generated: {payload['gitignore_covers_generated']}")
    if payload["is_git_repo"]:
        print(f"- git_dirty: {payload['git_dirty']}")
    print()
    print(payload["note"])
    print()
    for module in payload["modules"]:
        print(
            f"- {module['module_id']}  status={module['status']}  "
            f"installed={module['installed_version']}  available={module['available_version']}"
            f"{'  CUSTOM' if module['custom_override_active'] else ''}"
            f"{'  LOCAL EDITS' if module['files_with_local_edits'] else ''}"
        )
    return 0


def cmd_update_preview(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    rows = preview_updates_rich(workspace_root, module_id=args.module_id)
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("Nothing to preview.")
        return 0
    print("# Update preview\n")
    for row in rows:
        print(f"## {row['module_id']}")
        print(f"- status: {row['status']}")
        print(f"- installed: {row['installed_version']}")
        print(f"- available: {row['available_version']}")
        print(f"- risk: {row['risk_level']}")
        print(f"- recommended: {row['recommended_action']}")
        print(f"- summary: {row['human_summary']}")
        if row["files_with_local_edits"]:
            print(f"- local edits ({len(row['files_with_local_edits'])}):")
            for f in row["files_with_local_edits"][:10]:
                print(f"    {f}")
        print()
    return 0


def cmd_update_apply(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    result = apply_updates_safe(
        workspace_root,
        module_id=args.module_id,
        allow_local_edits=bool(args.allow_local_edits),
    )
    payload = {
        "backup_id": result.backup_id,
        "backup_dir": str(result.backup_dir),
        "applied_modules": result.applied_modules,
        "skipped_modules": result.skipped_modules,
        "changed_paths": result.changed_paths,
        "rollback_command": result.rollback_command,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"Applied updates. Backup: {result.backup_id}")
    print(f"  Applied: {result.applied_modules}")
    print(f"  Skipped: {[m['module_id'] for m in result.skipped_modules]}")
    print(f"  Changed paths: {len(result.changed_paths)}")
    print(f"  Rollback: {result.rollback_command}")
    return 0


def cmd_update_rollback(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    payload = rollback_update(workspace_root, args.backup_id)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"Rolled back to backup: {args.backup_id}")
    return 0


def add_update_subcommands(subparsers: argparse._SubParsersAction) -> None:
    update = subparsers.add_parser("update", help="Update managed modules (check / preview / apply / rollback)")
    update_sub = update.add_subparsers(dest="update_command", required=True)

    check = update_sub.add_parser("check", help="Status report (non-mutating)")
    check.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    check.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    check.set_defaults(func=cmd_update_check)

    preview = update_sub.add_parser("preview", help="Per-module preview with risk and recommendation")
    preview.add_argument("module_id", nargs="?")
    preview.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    preview.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    preview.set_defaults(func=cmd_update_preview)

    apply_p = update_sub.add_parser("apply", help="Apply safe managed updates (creates a backup)")
    apply_p.add_argument("module_id", nargs="?")
    apply_p.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    apply_p.add_argument(
        "--allow-local-edits",
        action="store_true",
        help="Apply even if managed files have local edits (default: skip).",
    )
    apply_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    apply_p.set_defaults(func=cmd_update_apply)

    rollback = update_sub.add_parser("rollback", help="Restore managed files from an update backup")
    rollback.add_argument("backup_id")
    rollback.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    rollback.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    rollback.set_defaults(func=cmd_update_rollback)
