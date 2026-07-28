"""CLI for ``sancho repair note`` -- record a durable repair entry."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sancho.modules import discover_module_map
from sancho.run_log import LOGS_DIRNAME, REPAIRS_LOG, ensure_logs_dir
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_repair_jsonl(logs_dir: Path, event: dict) -> None:
    path = logs_dir / REPAIRS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, default=str) + "\n")


def _append_repair_notes(custom_dir: Path, event: dict) -> Path:
    notes_path = custom_dir / "REPAIR_NOTES.md"
    header = f"## {event['timestamp']} -- run_id `{event['run_id']}`\n\n"
    body = f"{event['summary'].strip()}\n\n"
    if notes_path.exists():
        notes_path.write_text(notes_path.read_text(encoding="utf-8") + header + body, encoding="utf-8")
    else:
        notes_path.write_text(f"# Repair notes\n\n{header}{body}", encoding="utf-8")
    return notes_path


def cmd_repair_note(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    ensure_logs_dir(workspace_root)
    event = {
        "timestamp": _now_iso(),
        "event_type": "repair_note",
        "run_id": args.run_id or "",
        "module_id": args.module,
        "summary": args.summary.strip(),
    }
    logs_dir = workspace_root / LOGS_DIRNAME
    _append_repair_jsonl(logs_dir, event)

    notes_written: str | None = None
    custom = discover_module_map(workspace_root, zone="custom").get(args.module)
    if custom is not None:
        notes_path = _append_repair_notes(custom.module_dir, event)
        notes_written = str(notes_path)

    if getattr(args, "json", False):
        print(json.dumps({
            "jsonl": str(logs_dir / REPAIRS_LOG),
            "module_notes": notes_written,
            "event": event,
        }, indent=2))
        return 0
    print(f"Recorded repair note for {args.module} (run_id={args.run_id or '-'})")
    print(f"  appended to: {logs_dir / REPAIRS_LOG}")
    if notes_written:
        print(f"  appended to: {notes_written}")
    else:
        print("  (no custom override found; module-local REPAIR_NOTES.md skipped)")
    return 0


def add_repair_subcommands(subparsers: argparse._SubParsersAction) -> None:
    repair = subparsers.add_parser("repair", help="Repair-history utilities")
    repair_sub = repair.add_subparsers(dest="repair_command", required=True)

    note = repair_sub.add_parser("note", help="Record a durable note describing a repair")
    note.add_argument("--module", required=True, help="Module id, e.g. fetch.census.acs_profile")
    note.add_argument("--summary", required=True, help="Plain-language summary of what changed")
    note.add_argument("--run-id", help="Run id from logs/runs.jsonl (optional)")
    note.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    note.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    note.set_defaults(func=cmd_repair_note)
