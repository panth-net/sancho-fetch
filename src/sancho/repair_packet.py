"""Phase 6 repair packets: rich `errors/<run-id>_error.md` files.

Sancho writes one of these for every failed run so the agent (Claude/Codex)
or human operator can read a single file and know what failed, where to
patch, and how to retry -- without grepping logs or scanning the codebase.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.run_log import ERRORS_DIR, RunHandle, _iso
from sancho.runtime.redaction import (
    redact_sensitive_payload as _redact_payload,
    redact_sensitive_text as _redact,
)


def write_error_packet(
    handle: RunHandle,
    *,
    error_message: str,
    exception_text: str | None = None,
    extra: dict[str, Any] | None = None,
    http_status: int | None = None,
    response_excerpt: str | None = None,
    resolved_url: str | None = None,
    files_written: list[str] | None = None,
    cache_status_before: str | None = None,
    cache_status_after: str | None = None,
    last_successful_run: dict[str, Any] | None = None,
    docs_links: list[str] | None = None,
    suggested_override_path: str | None = None,
    safe_retry_command: str | None = None,
) -> Path:
    error_message = _redact(error_message) or error_message
    exception_text = _redact(exception_text)
    response_excerpt = _redact(response_excerpt)
    resolved_url = _redact(resolved_url)

    logs_dir = handle.logs_dir()
    errors_dir = logs_dir / ERRORS_DIR
    errors_dir.mkdir(parents=True, exist_ok=True)
    packet = errors_dir / f"{handle.run_id}_error.md"

    sections: list[str] = []
    sections.append(_header(handle))
    sections.append(_what_failed(error_message))
    if http_status is not None:
        sections.append(_http_section(http_status, resolved_url))
    if response_excerpt:
        sections.append(_response_section(response_excerpt))
    if exception_text:
        sections.append(_traceback_section(exception_text))
    if handle.request_summary:
        sections.append(_request_section(handle.request_summary))
    sections.append(_env_section(handle))
    if files_written:
        sections.append(_files_section(files_written))
    if cache_status_before or cache_status_after:
        sections.append(_cache_section(cache_status_before, cache_status_after))
    if last_successful_run:
        sections.append(_last_success_section(last_successful_run))
    if docs_links:
        sections.append(_docs_section(docs_links))
    if extra:
        sections.append(_notes_section(extra))
    sections.append(_next_steps_section(handle, suggested_override_path, safe_retry_command))

    packet.write_text("\n".join(s.rstrip() + "\n" for s in sections), encoding="utf-8")
    return packet


def _header(handle: RunHandle) -> str:
    lines = [
        f"# Sancho run error: {handle.module_id}",
        "",
        f"- run_id: `{handle.run_id}`",
        f"- module_id: `{handle.module_id}`",
        f"- module_source: `{handle.module_source}`",
        f"- module_version: `{handle.module_version}`",
        f"- module_path: `{handle.module_path}`",
        f"- started_at: {_iso(handle.started_at)}",
        f"- workspace: {handle.workspace_root}",
        f"- current_project: {handle.current_project_path}",
        f"- python: {platform.python_version()}",
        f"- platform: {platform.platform()}",
        f"- sancho_version: {SANCHO_VERSION}",
    ]
    return "\n".join(lines)


def _what_failed(error_message: str) -> str:
    return "\n".join(["## What failed", "", error_message])


def _http_section(status: int, url: str | None) -> str:
    return "\n".join([
        "## HTTP",
        "",
        f"- status: `{status}`",
        f"- resolved_url: `{url or '(unknown)'}`",
    ])


def _response_section(excerpt: str) -> str:
    return "\n".join([
        "## Provider response (truncated)",
        "",
        "```",
        excerpt[:2000],
        "```",
    ])


def _traceback_section(text: str) -> str:
    return "\n".join(["## Traceback", "", "```", text, "```"])


def _request_section(request_summary: Any) -> str:
    return "\n".join([
        "## Request",
        "",
        "```json",
        json.dumps(_redact_payload(request_summary), indent=2, default=str),
        "```",
    ])


def _env_section(handle: RunHandle) -> str:
    names = ", ".join(f"`{name}`" for name in handle.env_names) if handle.env_names else "(none)"
    return "\n".join([
        "## Environment keys present",
        "",
        names,
        "",
        "_Values are not recorded. Only key names are listed._",
    ])


def _files_section(files: list[str]) -> str:
    lines = ["## Files written before failure", ""]
    for f in files[:30]:
        lines.append(f"- `{f}`")
    if len(files) > 30:
        lines.append(f"- ... and {len(files) - 30} more")
    return "\n".join(lines)


def _cache_section(before: str | None, after: str | None) -> str:
    return "\n".join([
        "## Cache status",
        "",
        f"- before: {before or '(unknown)'}",
        f"- after:  {after or '(unknown)'}",
    ])


def _last_success_section(record: dict[str, Any]) -> str:
    return "\n".join([
        "## Last successful run",
        "",
        f"- run_id: `{record.get('run_id', '')}`",
        f"- finished_at: {record.get('finished_at', '')}",
        f"- row_count: {record.get('row_count', '?')}",
    ])


def _docs_section(links: list[str]) -> str:
    lines = ["## Docs / provider links", ""]
    for link in links:
        lines.append(f"- {link}")
    return "\n".join(lines)


def _notes_section(extra: dict[str, Any]) -> str:
    lines = ["## Notes", ""]
    for key, value in extra.items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines)


def _next_steps_section(
    handle: RunHandle,
    suggested_override_path: str | None,
    safe_retry_command: str | None,
) -> str:
    lines = [
        "## Suggested next steps",
        "",
        f"- Inspect the module: `{handle.module_path}`",
    ]
    if suggested_override_path:
        lines.append(
            f"- For a local fix, create a custom override at `{suggested_override_path}` "
            "(custom/** wins at runtime)."
        )
    else:
        lines.append(
            f"- For a local fix, create a custom override at `custom/{handle.module_source}/<module>/`."
        )
    if safe_retry_command:
        lines.append(f"- Safe retry: `{safe_retry_command}`")
    else:
        lines.append("- Re-run with the same input once the fix is in place.")
    lines.append(
        f"- Record what you changed: "
        f"`sancho repair note --run-id {handle.run_id} --module {handle.module_id} --summary \"...\"`."
    )
    return "\n".join(lines)
