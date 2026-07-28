"""CLI for ``sancho fetched-data audit``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sancho.modules import discover_module_map
from sancho.templates.runtime.cache_index import iter_cache_records
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def _fetched_data_root(workspace_root: Path) -> Path:
    return workspace_root / "fetched-data"


def audit_old_modules(workspace_root: Path) -> dict[str, Any]:
    """Report fetched-data records whose recorded module version is older than installed."""
    installed = discover_module_map(workspace_root)
    installed_versions = {mid: loc.version for mid, loc in installed.items()}

    rows = iter_cache_records(_fetched_data_root(workspace_root))
    findings: list[dict[str, Any]] = []
    by_status: dict[str, int] = {"older_than_installed": 0, "matches_installed": 0, "no_version_recorded": 0, "unknown_module": 0}
    for row in rows:
        # Re-read provenance.yml for the extended fields we recently added.
        record_dir = Path(row["record_dir"])
        prov_path = record_dir / "provenance.yml"
        meta: dict[str, Any] = {}
        if prov_path.exists():
            import yaml
            try:
                meta = yaml.safe_load(prov_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        recorded_version = str(meta.get("module_version") or "").strip()
        recorded_sancho = str(meta.get("sancho_version") or "").strip()
        recorded_source = str(meta.get("module_source") or "").strip()
        recorded_path = str(meta.get("module_path") or "").strip()
        module_id = row.get("module_id", "")
        installed_version = installed_versions.get(module_id)

        status = "matches_installed"
        if installed_version is None:
            status = "unknown_module"
        elif not recorded_version:
            status = "no_version_recorded"
        elif recorded_version != installed_version:
            status = "older_than_installed"
        by_status[status] = by_status.get(status, 0) + 1

        if status in {"older_than_installed", "no_version_recorded"}:
            findings.append({
                "record_id": row.get("record_id", ""),
                "record_dir": str(record_dir),
                "module_id": module_id,
                "recorded_module_version": recorded_version,
                "recorded_sancho_version": recorded_sancho,
                "recorded_module_source": recorded_source,
                "recorded_module_path": recorded_path,
                "currently_installed_version": installed_version,
                "fetched_at": row.get("fetched_at", ""),
                "status": status,
            })

    return {
        "workspace_root": str(workspace_root),
        "total_records_scanned": len(rows),
        "counts_by_status": by_status,
        "findings": findings,
        "note": "Old records are reported but not auto-invalidated. Refetch only what you need.",
    }


def cmd_fetched_data_audit(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    if not args.old_modules:
        print("Pass --old-modules to scan for cache records fetched with older module versions.")
        return 1
    payload = audit_old_modules(workspace_root)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"Records scanned: {payload['total_records_scanned']}")
    counts = payload["counts_by_status"]
    for status, count in counts.items():
        print(f"  {status}: {count}")
    print()
    for finding in payload["findings"]:
        print(
            f"- {finding['module_id']}  recorded={finding['recorded_module_version'] or '(none)'}  "
            f"installed={finding['currently_installed_version']}  "
            f"record_id={finding['record_id']}"
        )
    return 0


def add_fetched_data_subcommands(subparsers: argparse._SubParsersAction) -> None:
    fd = subparsers.add_parser("fetched-data", help="Inspect the canonical fetched-data store")
    fd_sub = fd.add_subparsers(dest="fetched_data_command", required=True)

    audit = fd_sub.add_parser("audit", help="Audit fetched-data records (versions, drift)")
    audit.add_argument("--old-modules", action="store_true", help="Show records fetched with older module versions")
    audit.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    audit.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    audit.set_defaults(func=cmd_fetched_data_audit)
