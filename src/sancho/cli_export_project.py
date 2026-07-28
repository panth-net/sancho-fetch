"""CLI for ``sancho export-to-project``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sancho.cli_cache import _find_record_by_id, _fetched_data_root
from sancho.config import load_workspace_config
from sancho.project_export import export_records_to_public_outputs
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


def _collect_record_dirs(workspace_root: Path, args: argparse.Namespace) -> list[Path] | None:
    cache_records = args.cache_record or []
    if isinstance(cache_records, str):
        cache_records = [cache_records]
    if cache_records:
        dirs: list[Path] = []
        for record_id in cache_records:
            record_dir = _find_record_by_id(workspace_root, record_id)
            if record_dir is None:
                print(f"No cache record matched: {record_id}", file=sys.stderr)
                return None
            dirs.append(record_dir)
        return dirs
    if args.run_id:
        record_dir = _find_record_for_run(workspace_root, args.run_id)
        if record_dir is None:
            print(
                f"No cache record found for run_id {args.run_id}. "
                "Run the module first, or pass --cache-record directly.",
                file=sys.stderr,
            )
            return None
        return [record_dir]
    print("Pass either --cache-record <id> (repeatable) or --run-id <id>.", file=sys.stderr)
    return None


def cmd_export_to_project(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    project_root = Path(args.project).resolve()

    record_dirs = _collect_record_dirs(workspace_root, args)
    if record_dirs is None:
        return 1

    labels = [args.label] if args.label and len(record_dirs) == 1 else None
    config = load_workspace_config(workspace_root)
    result = export_records_to_public_outputs(
        record_dirs=record_dirs,
        project_root=project_root,
        workspace_root=workspace_root,
        labels=labels,
        config=config,
        unit_sources=["reused_cache"] * len(record_dirs),
    )

    if getattr(args, "json", False):
        print(json.dumps({
            "primary_output_path": str(result.primary_path),
            "output_paths": [str(p) for p in result.output_paths],
            "mode": result.mode,
            "canonical_record_dirs": [str(p) for p in result.canonical_record_dirs],
        }, indent=2, default=str))
        return 0

    label = "Primary folder" if result.mode != "single_file" else "Primary file"
    print(f"{label}:")
    print(str(result.primary_path))
    for big in result.large_files:
        size_mb = big.get("bytes", 0) / (1024 * 1024)
        print(
            f"\nHeads-up: {Path(big['path']).name} is {size_mb:.1f} MB. You now have your "
            f"own copy above. If you need disk space back later, it's safe to delete the "
            f"cached copy at {big.get('cached_path', '')}.",
            file=sys.stderr,
        )
    return 0


def add_export_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "export-to-project",
        help="Write a cached record into a project's 'sancho-downloads/' folder",
    )
    parser.add_argument(
        "--cache-record",
        action="append",
        help="Cache record id (module/family/key/timestamp) or request_key. Repeatable.",
    )
    parser.add_argument("--run-id", help="Run id from logs/runs.jsonl (resolves the run's record)")
    parser.add_argument("--project", default=".", help="Destination project folder (default: CWD)")
    parser.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    parser.add_argument("--label", help="Optional short label for the output file (single record only)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.set_defaults(func=cmd_export_to_project)
