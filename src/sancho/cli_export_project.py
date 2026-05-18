"""CLI for ``sancho export-to-project``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sancho.cli_cache import _find_record_by_id, _fetched_data_root
from sancho.project_export import export_record_to_project
from sancho.run_log import LOGS_DIRNAME, RUNS_LOG
from sancho.templates.runtime.cache_index import iter_cache_records
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def _fetched_at(rec: dict) -> str:
    return rec.get("fetched_at", "")


def _find_record_for_run(workspace_root: Path, run_id: str) -> Path | None:
    """Best-effort: find the most recent cache record produced by a run."""
    runs_log = workspace_root / LOGS_DIRNAME / RUNS_LOG
    if not runs_log.exists():
        return None
    target_module = None
    target_finished_at: str | None = None
    for line in runs_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("run_id") != run_id:
            continue
        if event.get("event_type") == "run_finished":
            target_finished_at = event.get("finished_at") or ""
            target_module = event.get("module_id") or ""
    if not target_module:
        return None

    records = [
        r for r in iter_cache_records(_fetched_data_root(workspace_root))
        if r.get("module_id") == target_module
    ]
    if not records:
        return None
    if target_finished_at:
        leq = [r for r in records if _fetched_at(r) <= target_finished_at]
        if leq:
            leq.sort(key=_fetched_at, reverse=True)
            return Path(leq[0]["record_dir"])
    records.sort(key=_fetched_at, reverse=True)
    return Path(records[0]["record_dir"])


def cmd_export_to_project(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    project_root = Path(args.project).resolve()

    if args.cache_record:
        record_dir = _find_record_by_id(workspace_root, args.cache_record)
        if record_dir is None:
            print(f"No cache record matched: {args.cache_record}", file=sys.stderr)
            return 1
    elif args.run_id:
        record_dir = _find_record_for_run(workspace_root, args.run_id)
        if record_dir is None:
            print(
                f"No cache record found for run_id {args.run_id}. "
                "Run the module first, or pass --cache-record directly.",
                file=sys.stderr,
            )
            return 1
    else:
        print("Pass either --cache-record <id> or --run-id <id>.", file=sys.stderr)
        return 1

    result = export_record_to_project(
        record_dir=record_dir,
        project_root=project_root,
        workspace_root=workspace_root,
        label=args.label,
    )
    if getattr(args, "json", False):
        print(json.dumps({
            "bundle_dir": str(result.bundle_dir),
            "mode": result.mode,
            "record_dirs": [str(p) for p in result.record_dirs],
            "bytes_written": result.bytes_written,
        }, indent=2, default=str))
        return 0
    print(f"Exported bundle: {result.bundle_dir}")
    print(f"  mode: {result.mode}")
    print(f"  bytes: {result.bytes_written}")
    print(f"  records: {len(result.record_dirs)}")
    return 0


def add_export_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "export-to-project",
        help="Copy a cached record into a project's 'sancho-fetched-data/' folder",
    )
    parser.add_argument("--cache-record", help="Cache record id (module/family/key/timestamp) or just request_key")
    parser.add_argument("--run-id", help="Run id from logs/runs.jsonl (matches latest cache record for that module)")
    parser.add_argument("--project", default=".", help="Destination project folder (default: CWD)")
    parser.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    parser.add_argument("--label", help="Optional human label appended to the bundle folder name")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.set_defaults(func=cmd_export_to_project)
