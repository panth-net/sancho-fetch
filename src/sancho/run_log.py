"""Visible run logs for Sancho Fetch.

Each fetch/run writes one or more events to ``sancho-workspace/logs/`` so
both the user and Claude/Codex can inspect what happened without trusting an
opaque ``complete: true`` flag.

File layout::

    sancho-workspace/logs/
        README.md
        runs.jsonl         # one line per started/finished run
        fetches.jsonl      # network/cache fetch events (currently piggybacks on runs)
        cache-events.jsonl # cache save/load events
        errors.jsonl       # failed runs (subset of runs.jsonl, filtered)
        repairs.jsonl      # human/agent-authored repair notes (Phase 6)
        latest.md          # plain-language summary of the last run
        errors/
            <run-id>_error.md   # repair packet for each failed run

API keys are NEVER logged -- only the set of env-var names that were
populated. ``begin_run`` takes a list of ``env_names`` (key names without
values); ``write_error_packet`` consults the same list and never reads
values.
"""

from __future__ import annotations

import json
import platform
import secrets
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.runtime.redaction import (
    redact_sensitive_payload as _redact_sensitive_payload,
    redact_sensitive_text as _redact_sensitive_text,
)

LOGS_DIRNAME = "logs"

RUNS_LOG = "runs.jsonl"
FETCHES_LOG = "fetches.jsonl"
CACHE_EVENTS_LOG = "cache-events.jsonl"
ERRORS_LOG = "errors.jsonl"
REPAIRS_LOG = "repairs.jsonl"
LATEST_MD = "latest.md"
ERRORS_DIR = "errors"
LOGS_README = "README.md"

_LOGS_README_TEXT = """# Sancho Fetch logs

Every fetch/run writes one or more events here so you and your AI agent
can debug without trusting an opaque "complete" flag.

- `runs.jsonl` -- append-only event log: one line per run-start and run-finish.
- `fetches.jsonl` -- fetch-specific events (cache hits, misses, network calls).
- `cache-events.jsonl` -- cache save/load events.
- `errors.jsonl` -- failed runs only. Each entry points at a repair packet.
- `repairs.jsonl` -- `sancho repair note` entries (Phase 6).
- `latest.md` -- short plain-language summary of the most recent run.
- `errors/<run-id>_error.md` -- one repair packet per failed run.

API keys are never written to these files. We only record which key NAMES
were present at run time (e.g. `FRED_API_KEY: present`).
"""


@dataclass
class RunHandle:
    run_id: str
    workspace_root: Path
    started_at: datetime
    module_id: str
    module_source: str
    module_version: str
    module_path: str
    request_summary: dict[str, Any]
    env_names: list[str]
    current_project_path: str

    def logs_dir(self) -> Path:
        return self.workspace_root / LOGS_DIRNAME


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _new_run_id(now: datetime) -> str:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, default=str) + "\n")


def ensure_logs_dir(workspace_root: Path) -> Path:
    logs_dir = workspace_root / LOGS_DIRNAME
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / ERRORS_DIR).mkdir(parents=True, exist_ok=True)
    readme = logs_dir / LOGS_README
    if not readme.exists():
        readme.write_text(_LOGS_README_TEXT, encoding="utf-8")
    return logs_dir


def _safe_request_summary(payload: Any, max_chars: int = 4_000) -> Any:
    """Truncate large request payloads so logs stay small. Returns JSON-safe data."""
    payload = _redact_sensitive_payload(payload)
    try:
        text = json.dumps(payload, default=str)
    except Exception:
        return {"_unprintable": True}
    if len(text) <= max_chars:
        return payload
    return {"_truncated": True, "preview": text[:max_chars]}


def _redact_env_value(value: str, secrets_seen: list[str]) -> str:
    if not value:
        return value
    for secret in secrets_seen:
        if secret and secret in value:
            value = value.replace(secret, "[REDACTED]")
    return value


def begin_run(
    workspace_root: Path,
    *,
    module_id: str,
    module_source: str,
    module_version: str,
    module_path: str,
    request_summary: Any,
    env_names: list[str],
    current_project_path: str | None = None,
) -> RunHandle:
    ensure_logs_dir(workspace_root)
    now = _now()
    run_id = _new_run_id(now)
    handle = RunHandle(
        run_id=run_id,
        workspace_root=workspace_root,
        started_at=now,
        module_id=module_id,
        module_source=module_source,
        module_version=module_version,
        module_path=module_path,
        request_summary=_safe_request_summary(request_summary),
        env_names=sorted(set(env_names)),
        current_project_path=current_project_path or str(Path.cwd().resolve()),
    )
    event = {
        "timestamp": _iso(now),
        "run_id": run_id,
        "event_type": "run_started",
        "module_id": module_id,
        "module_source": module_source,
        "module_version": module_version,
        "module_path": module_path,
        "workspace_path": str(workspace_root),
        "current_project_path": handle.current_project_path,
        "request_summary": handle.request_summary,
        "env_present": handle.env_names,
        "sancho_version": SANCHO_VERSION,
    }
    _append_jsonl(handle.logs_dir() / RUNS_LOG, event)
    return handle


def _write_latest(workspace_root: Path, summary: dict[str, Any]) -> None:
    logs_dir = workspace_root / LOGS_DIRNAME
    logs_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Last Sancho run",
        "",
        f"- run_id: `{summary.get('run_id', '')}`",
        f"- module_id: `{summary.get('module_id', '')}`",
        f"- status: `{summary.get('status', '')}`",
        f"- started_at: {summary.get('started_at', '')}",
        f"- finished_at: {summary.get('finished_at', '')}",
        f"- row_count: {summary.get('row_count', '?')}",
    ]
    if summary.get("error_message"):
        lines.append(f"- error_message: {summary['error_message']}")
    if summary.get("repair_packet_path"):
        lines.append(f"- repair_packet: `{summary['repair_packet_path']}`")
    lines.append("")
    (logs_dir / LATEST_MD).write_text("\n".join(lines), encoding="utf-8")


def finish_run(
    handle: RunHandle,
    *,
    status: str,
    row_count: int | None = None,
    files_written: list[str] | None = None,
    cache_status: str | None = None,
    error_message: str | None = None,
    repair_packet_path: str | None = None,
) -> dict[str, Any]:
    now = _now()
    error_message = _redact_sensitive_text(error_message)
    summary = {
        "timestamp": _iso(now),
        "run_id": handle.run_id,
        "event_type": "run_finished",
        "module_id": handle.module_id,
        "module_source": handle.module_source,
        "module_version": handle.module_version,
        "module_path": handle.module_path,
        "workspace_path": str(handle.workspace_root),
        "current_project_path": handle.current_project_path,
        "request_summary": handle.request_summary,
        "status": status,
        "row_count": row_count,
        "files_written": files_written or [],
        "cache_status": cache_status,
        "error_message": error_message,
        "repair_packet_path": repair_packet_path,
        "started_at": _iso(handle.started_at),
        "finished_at": _iso(now),
        "duration_seconds": (now - handle.started_at).total_seconds(),
        "sancho_version": SANCHO_VERSION,
    }
    logs_dir = handle.logs_dir()
    _append_jsonl(logs_dir / RUNS_LOG, summary)
    if status not in {"success_with_data", "success_empty"}:
        _append_jsonl(logs_dir / ERRORS_LOG, summary)
    _write_latest(handle.workspace_root, summary)
    return summary


def record_cache_event(
    workspace_root: Path,
    *,
    event: str,
    module_id: str,
    record_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    ensure_logs_dir(workspace_root)
    payload = {
        "timestamp": _iso(_now()),
        "event_type": event,
        "module_id": module_id,
        "record_id": record_id,
        "detail": detail or {},
    }
    _append_jsonl(workspace_root / LOGS_DIRNAME / CACHE_EVENTS_LOG, payload)


def record_run_event(
    workspace_root: Path,
    *,
    event_type: str,
    module_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    ensure_logs_dir(workspace_root)
    payload = {
        "timestamp": _iso(_now()),
        "event_type": event_type,
        "module_id": module_id,
        "detail": _redact_sensitive_payload(detail or {}),
        "sancho_version": SANCHO_VERSION,
    }
    _append_jsonl(workspace_root / LOGS_DIRNAME / RUNS_LOG, payload)
