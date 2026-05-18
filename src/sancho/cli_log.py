"""CLI for ``sancho log path / tail / show / search``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from sancho.run_log import (
    CACHE_EVENTS_LOG,
    ERRORS_LOG,
    LOGS_DIRNAME,
    LATEST_MD,
    RUNS_LOG,
    ensure_logs_dir,
)
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _print_events_human(events: Iterable[dict]) -> None:
    for event in events:
        ts = event.get("timestamp", "")
        run_id = event.get("run_id", "")
        kind = event.get("event_type", "")
        module = event.get("module_id", "")
        status = event.get("status") or ""
        rows = event.get("row_count")
        err = event.get("error_message")
        suffix = ""
        if status:
            suffix += f" status={status}"
        if rows is not None:
            suffix += f" rows={rows}"
        if err:
            suffix += f"  ! {err}"
        print(f"{ts}  {kind:<14} {run_id}  {module}{suffix}")


def cmd_log_path(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    ensure_logs_dir(workspace_root)
    print(workspace_root / LOGS_DIRNAME)
    return 0


def cmd_log_tail(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    logs_dir = workspace_root / LOGS_DIRNAME
    target = logs_dir / (ERRORS_LOG if args.errors else RUNS_LOG)
    events = _read_jsonl(target)
    if args.module:
        events = [e for e in events if e.get("module_id") == args.module]
    events = events[-int(args.limit):]
    if getattr(args, "json", False):
        print(json.dumps(events, indent=2, default=str))
        return 0
    if not events:
        print(f"No log entries in {target}")
        return 0
    _print_events_human(events)
    return 0


def cmd_log_show(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    logs_dir = workspace_root / LOGS_DIRNAME
    runs = _read_jsonl(logs_dir / RUNS_LOG)
    matching = [e for e in runs if e.get("run_id") == args.run_id]
    if not matching:
        print(f"No log entries for run_id {args.run_id}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(matching, indent=2, default=str))
        return 0
    for event in matching:
        print(json.dumps(event, indent=2, default=str))
        print("---")
    # Show repair packet if it exists
    last = matching[-1]
    packet = last.get("repair_packet_path")
    if packet:
        packet_path = Path(packet)
        if packet_path.exists():
            print()
            print(f"Repair packet ({packet_path}):")
            print(packet_path.read_text(encoding="utf-8"))
    return 0


def cmd_log_search(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    logs_dir = workspace_root / LOGS_DIRNAME
    sources = [logs_dir / RUNS_LOG, logs_dir / ERRORS_LOG, logs_dir / CACHE_EVENTS_LOG]
    events: list[dict] = []
    for src in sources:
        for e in _read_jsonl(src):
            if args.module and e.get("module_id") != args.module:
                continue
            if args.query and args.query not in json.dumps(e, default=str):
                continue
            events.append(e)
    events.sort(key=lambda e: e.get("timestamp", ""))
    if getattr(args, "json", False):
        print(json.dumps(events, indent=2, default=str))
        return 0
    if not events:
        print("No log entries matched.")
        return 0
    _print_events_human(events)
    return 0


def add_log_subcommands(subparsers: argparse._SubParsersAction) -> None:
    log = subparsers.add_parser("log", help="Inspect Sancho run/fetch/error logs")
    log_sub = log.add_subparsers(dest="log_command", required=True)

    pathc = log_sub.add_parser("path", help="Print the path to the logs folder")
    pathc.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    pathc.set_defaults(func=cmd_log_path)

    tail = log_sub.add_parser("tail", help="Show the last N run entries (use --errors for errors only)")
    tail.add_argument("--errors", action="store_true", help="Show errors only")
    tail.add_argument("--module", help="Filter to a single module id")
    tail.add_argument("--limit", default="20", help="Number of entries to show (default 20)")
    tail.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    tail.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    tail.set_defaults(func=cmd_log_tail)

    show = log_sub.add_parser("show", help="Show every event for one run_id")
    show.add_argument("run_id", help="Run id (timestamp-suffix)")
    show.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    show.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    show.set_defaults(func=cmd_log_show)

    search = log_sub.add_parser("search", help="Search log entries across runs/errors/cache events")
    search.add_argument("--module", help="Filter by module id")
    search.add_argument("--query", help="Free-text substring to match within event JSON")
    search.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    search.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    search.set_defaults(func=cmd_log_search)
