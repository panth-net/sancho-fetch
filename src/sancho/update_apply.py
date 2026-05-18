"""Phase 8 apply + rollback: backups, lock snapshots, update log entries."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.modules import apply_updates as _apply_updates_low

UPDATE_BACKUPS_DIR = "update-backups"
UPDATE_LOG = "update-log.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


@dataclass
class ApplyResult:
    backup_id: str
    backup_dir: Path
    applied_modules: list[str]
    skipped_modules: list[dict[str, Any]]
    changed_paths: list[str]
    rollback_command: str


def _allocate_backup_dir(workspace_root: Path) -> tuple[str, Path]:
    base = workspace_root / UPDATE_BACKUPS_DIR
    base.mkdir(parents=True, exist_ok=True)
    today = _now().strftime("%Y-%m-%d")
    counter = 1
    while True:
        backup_id = f"{today}-update-{counter:03d}"
        candidate = base / backup_id
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return backup_id, candidate
        counter += 1


def _snapshot_source(workspace_root: Path, dest: Path) -> None:
    source_dir = workspace_root / "source"
    if not source_dir.exists():
        return
    shutil.copytree(source_dir, dest / "source-before")


def _save_lock_snapshot(workspace_root: Path, dest: Path) -> None:
    lock_path = workspace_root / "modules.lock.yaml"
    if lock_path.exists():
        shutil.copy2(lock_path, dest / "modules.lock.before.yaml")


def _write_preview_md(preview: list[dict[str, Any]], dest: Path) -> None:
    lines = ["# Update preview", ""]
    for row in preview:
        lines.append(f"## {row['module_id']}")
        lines.append("")
        lines.append(f"- status: {row['status']}")
        lines.append(f"- installed: {row['installed_version']}")
        lines.append(f"- available: {row['available_version']}")
        lines.append(f"- risk: {row['risk_level']}")
        lines.append(f"- recommended: {row['recommended_action']}")
        lines.append(f"- summary: {row['human_summary']}")
        if row["files_with_local_edits"]:
            lines.append(f"- local edits: {row['files_with_local_edits']}")
        lines.append("")
    (dest / "update-preview.md").write_text("\n".join(lines), encoding="utf-8")


def _write_result_md(result: ApplyResult, dest: Path) -> None:
    lines = [
        "# Update result",
        "",
        f"- backup_id: `{result.backup_id}`",
        f"- applied: {result.applied_modules}",
        f"- skipped: {[m['module_id'] for m in result.skipped_modules]}",
        f"- changed_paths: {len(result.changed_paths)}",
        f"- rollback: `{result.rollback_command}`",
        "",
    ]
    (dest / "update-result.md").write_text("\n".join(lines), encoding="utf-8")


def _append_update_log(workspace_root: Path, payload: dict[str, Any]) -> None:
    logs_dir = workspace_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / UPDATE_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def perform_apply(
    workspace_root: Path,
    preview: list[dict[str, Any]],
    *,
    allow_local_edits: bool,
) -> ApplyResult:
    actionable = [
        row for row in preview
        if row["recommended_action"] in {"apply", "review_local_edits_then_apply"}
    ]
    skipped: list[dict[str, Any]] = []
    to_apply: list[dict[str, Any]] = []
    for row in actionable:
        if row["personal_paths_touched"]:
            skipped.append({"module_id": row["module_id"], "reason": "would_touch_personal_path"})
            continue
        if row["files_with_local_edits"] and not allow_local_edits:
            skipped.append({"module_id": row["module_id"], "reason": "local_edits_present"})
            continue
        to_apply.append(row)
    for row in preview:
        if row not in actionable:
            skipped.append({"module_id": row["module_id"], "reason": row["status"]})

    backup_id, backup_dir = _allocate_backup_dir(workspace_root)
    _snapshot_source(workspace_root, backup_dir)
    _save_lock_snapshot(workspace_root, backup_dir)
    _write_preview_md(preview, backup_dir)

    low_level_actions = [
        {"module_id": row["module_id"], "action": "upgrade_available"}
        for row in to_apply
    ]
    changed = _apply_updates_low(workspace_root, low_level_actions) if low_level_actions else []
    rollback_command = f"sancho update rollback {backup_id} --workspace {workspace_root}"
    result = ApplyResult(
        backup_id=backup_id,
        backup_dir=backup_dir,
        applied_modules=[row["module_id"] for row in to_apply],
        skipped_modules=skipped,
        changed_paths=changed,
        rollback_command=rollback_command,
    )
    _write_result_md(result, backup_dir)
    _append_update_log(workspace_root, {
        "timestamp": _iso(_now()),
        "event": "update_applied",
        "backup_id": backup_id,
        "applied": result.applied_modules,
        "skipped": skipped,
        "changed_paths": changed,
        "sancho_version": SANCHO_VERSION,
    })
    return result


def rollback_update(workspace_root: Path, backup_id: str) -> dict[str, Any]:
    backup_dir = workspace_root / UPDATE_BACKUPS_DIR / backup_id
    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup not found: {backup_dir}")
    snapshot = backup_dir / "source-before"
    if not snapshot.exists():
        raise FileNotFoundError(f"Backup is incomplete (no source-before): {backup_dir}")

    source_dir = workspace_root / "source"
    if source_dir.exists():
        shutil.rmtree(source_dir)
    shutil.copytree(snapshot, source_dir)

    lock_snapshot = backup_dir / "modules.lock.before.yaml"
    if lock_snapshot.exists():
        shutil.copy2(lock_snapshot, workspace_root / "modules.lock.yaml")

    payload = {
        "timestamp": _iso(_now()),
        "event": "update_rolled_back",
        "backup_id": backup_id,
        "sancho_version": SANCHO_VERSION,
    }
    _append_update_log(workspace_root, payload)
    return payload
