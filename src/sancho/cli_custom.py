"""CLI for ``sancho custom status / retire`` and ``sancho module compare``."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from sancho.modules import discover_module_map, load_template_registry
from sancho.workspace import find_workspace_root

RETIRED_DIRNAME = "_retired"


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def _compare_version(a: str, b: str) -> int:
    try:
        va, vb = Version(a), Version(b)
    except InvalidVersion:
        return 0
    if va > vb:
        return 1
    if va < vb:
        return -1
    return 0


def _custom_status_payload(workspace_root: Path) -> dict[str, Any]:
    custom = discover_module_map(workspace_root, zone="custom")
    source = discover_module_map(workspace_root, zone="source")
    template_registry = load_template_registry()
    rows: list[dict[str, Any]] = []
    for module_id in sorted(custom.keys()):
        loc = custom[module_id]
        src_loc = source.get(module_id)
        template = template_registry.get(module_id)
        shadowing_source = src_loc is not None
        upstream_version = template.version if template else None
        custom_version = loc.version
        upstream_newer = False
        if upstream_version:
            upstream_newer = _compare_version(upstream_version, custom_version) > 0
        rows.append({
            "module_id": module_id,
            "custom_version": custom_version,
            "custom_path": str(loc.module_dir),
            "shadows_source": shadowing_source,
            "source_version": src_loc.version if src_loc else None,
            "template_available_version": upstream_version,
            "upstream_newer_than_custom": upstream_newer,
            "recommendation": (
                "compare_or_retire"
                if upstream_newer
                else ("active_override" if shadowing_source else "standalone_custom")
            ),
        })
    return {
        "workspace_root": str(workspace_root),
        "custom_count": len(rows),
        "custom_modules": rows,
    }


def cmd_custom_status(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    payload = _custom_status_payload(workspace_root)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"Custom modules: {payload['custom_count']}")
    for row in payload["custom_modules"]:
        marker = ""
        if row["upstream_newer_than_custom"]:
            marker = " (UPSTREAM NEWER -- consider compare/retire)"
        elif row["shadows_source"]:
            marker = " (active override)"
        print(f"- {row['module_id']}  v{row['custom_version']}{marker}")
        if row["template_available_version"]:
            print(f"    template available: v{row['template_available_version']}")
    return 0


def cmd_custom_retire(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    custom = discover_module_map(workspace_root, zone="custom").get(args.module_id)
    if custom is None:
        print(f"No custom module installed: {args.module_id}", file=sys.stderr)
        return 1
    retired_root = workspace_root / "custom" / RETIRED_DIRNAME
    retired_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = retired_root / f"{custom.module_dir.name}__{stamp}"
    shutil.move(str(custom.module_dir), str(dest))
    if getattr(args, "json", False):
        print(json.dumps({"retired_to": str(dest), "module_id": args.module_id}, indent=2))
        return 0
    print(f"Retired custom module: {args.module_id}")
    print(f"  moved to: {dest}")
    print("Original is recoverable; rerun 'sancho add' to reinstall the upstream version.")
    return 0


def _diff_text(left: str, right: str, left_label: str, right_label: str) -> str:
    return "".join(
        difflib.unified_diff(
            left.splitlines(keepends=True),
            right.splitlines(keepends=True),
            fromfile=left_label,
            tofile=right_label,
        )
    )


def cmd_module_compare(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    custom = discover_module_map(workspace_root, zone="custom").get(args.module_id)
    source = discover_module_map(workspace_root, zone="source").get(args.module_id)
    template = load_template_registry().get(args.module_id)
    if custom is None and template is None and source is None:
        print(f"Module not found: {args.module_id}", file=sys.stderr)
        return 1

    summary: dict[str, Any] = {
        "module_id": args.module_id,
        "custom_path": str(custom.module_dir) if custom else None,
        "source_path": str(source.module_dir) if source else None,
        "template_path": str(template.template_dir) if template else None,
        "diff_files": [],
    }

    # Compare custom <-> template (the most common case).
    if custom and template:
        custom_files = {p.relative_to(custom.module_dir).as_posix(): p for p in custom.module_dir.rglob("*") if p.is_file()}
        template_files = {p.relative_to(template.template_dir).as_posix(): p for p in template.template_dir.rglob("*") if p.is_file()}
        all_keys = sorted(set(custom_files) | set(template_files))
        for key in all_keys:
            left = template_files.get(key)
            right = custom_files.get(key)
            if left is None:
                summary["diff_files"].append({"path": key, "status": "only_in_custom"})
                continue
            if right is None:
                summary["diff_files"].append({"path": key, "status": "only_in_template"})
                continue
            try:
                left_text = left.read_text(encoding="utf-8")
                right_text = right.read_text(encoding="utf-8")
            except Exception:
                summary["diff_files"].append({"path": key, "status": "binary_or_unreadable"})
                continue
            if left_text == right_text:
                continue
            summary["diff_files"].append({
                "path": key,
                "status": "modified",
                "diff": _diff_text(left_text, right_text, f"template/{key}", f"custom/{key}"),
            })

    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2, default=str))
        return 0

    print(f"# Compare {args.module_id}")
    if not summary["diff_files"]:
        print("No differences between custom and template.")
        return 0
    for row in summary["diff_files"]:
        print(f"\n--- {row['path']}: {row['status']} ---")
        if "diff" in row:
            print(row["diff"][:8000])
    return 0


def add_custom_subcommands(subparsers: argparse._SubParsersAction) -> None:
    custom = subparsers.add_parser("custom", help="Inspect or retire custom overrides")
    custom_sub = custom.add_subparsers(dest="custom_command", required=True)

    status = custom_sub.add_parser("status", help="List custom modules and shadowing status")
    status.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    status.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    status.set_defaults(func=cmd_custom_status)

    retire = custom_sub.add_parser("retire", help="Move a custom module to custom/_retired/")
    retire.add_argument("module_id")
    retire.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    retire.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    retire.set_defaults(func=cmd_custom_retire)


def add_module_compare_subcommand(module_sub: argparse._SubParsersAction) -> None:
    compare = module_sub.add_parser("compare", help="Diff a custom override against the template")
    compare.add_argument("module_id")
    compare.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    compare.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    compare.set_defaults(func=cmd_module_compare)
