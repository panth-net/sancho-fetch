"""Phase 8 update engine: check + preview entry points.

Safety contract:

- Never touches ``custom/**``, ``playbooks/**``, ``fetched-data/**``,
  ``analysis-data/**``, ``outputs/**``, ``logs/**``, ``update-backups/**``,
  ``.env``, ``AI_INSTRUCTIONS.md``, ``DATASET_CATALOG.md``.

Apply/rollback live in :mod:`sancho.update_apply` to keep this file small.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.config import load_lock_config
from sancho.modules import (
    discover_module_map,
    load_template_registry,
    normalize_rel,
)
from sancho.release import WORKSPACE_SCHEMA_VERSION
from sancho.update_apply import (
    ApplyResult,
    perform_apply,
    rollback_update,
)
from sancho.utils import file_sha256

PERSONAL_PATH_PREFIXES = (
    "custom/",
    "playbooks/",
    "fetched-data/",
    "analysis-data/",
    "outputs/",
    "logs/",
    "update-backups/",
    "AI_INSTRUCTIONS.md",
    "DATASET_CATALOG.md",
    ".env",
)


def _is_personal_path(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in PERSONAL_PATH_PREFIXES)


def _git_status_dirty(workspace_root: Path) -> bool | None:
    repo_root = workspace_root.parent
    if not (repo_root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return bool([line for line in result.stdout.splitlines() if line.strip()])


def _gitignore_covers_generated(workspace_root: Path) -> bool:
    gitignore = workspace_root.parent / ".gitignore"
    if not gitignore.exists():
        return False
    text = gitignore.read_text(encoding="utf-8", errors="replace")
    return all(piece in text for piece in ("fetched-data/", "logs/", "update-backups/"))


def _files_with_local_edits(workspace_root: Path, lock_entry: dict[str, Any]) -> list[str]:
    edits: list[str] = []
    checksums = lock_entry.get("checksums") or {}
    for rel_path, expected in checksums.items():
        candidate = workspace_root / rel_path
        if not candidate.exists():
            edits.append(rel_path)
            continue
        if file_sha256(candidate) != expected:
            edits.append(rel_path)
    return sorted(edits)


def check_updates(workspace_root: Path) -> dict[str, Any]:
    """Comprehensive status report. Non-mutating."""
    registry = load_template_registry()
    installed = discover_module_map(workspace_root, zone="source")
    custom = discover_module_map(workspace_root, zone="custom")
    lock = load_lock_config(workspace_root)

    modules_status: list[dict[str, Any]] = []
    for module_id in sorted(installed.keys()):
        location = installed[module_id]
        template = registry.get(module_id)
        lock_entry = lock.get("modules", {}).get(module_id, {})
        installed_version = location.version
        available_version = template.version if template else None
        custom_override = module_id in custom
        local_edits = _files_with_local_edits(workspace_root, lock_entry)

        status = "current"
        if custom_override:
            status = "custom_override_active"
        elif available_version and available_version != installed_version:
            status = "update_available"
        elif local_edits:
            status = "review_needed"

        modules_status.append({
            "module_id": module_id,
            "installed_version": installed_version,
            "available_version": available_version,
            "status": status,
            "custom_override_active": custom_override,
            "files_with_local_edits": local_edits,
            "managed_path_count": len(lock_entry.get("checksums", {})),
        })

    return {
        "sancho_version": SANCHO_VERSION,
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "workspace_root": str(workspace_root),
        "env_present": (workspace_root / ".env").exists(),
        "gitignore_covers_generated": _gitignore_covers_generated(workspace_root),
        "is_git_repo": (workspace_root.parent / ".git").exists(),
        "git_dirty": _git_status_dirty(workspace_root),
        "modules": modules_status,
        "module_count": len(modules_status),
        "updatable_count": sum(1 for m in modules_status if m["status"] == "update_available"),
        "personal_paths_touched_by_update": [],
        "note": (
            "personal/generated paths "
            f"({', '.join(PERSONAL_PATH_PREFIXES)}) "
            "are never touched by 'sancho update apply'."
        ),
    }


def _human_summary(record: dict[str, Any]) -> str:
    status = record["status"]
    mid = record["module_id"]
    if status == "current":
        return f"{mid} is up to date."
    if status == "update_available":
        return (
            f"{mid} update available: "
            f"{record['installed_version']} -> {record['available_version']}."
        )
    if status == "custom_override_active":
        return f"{mid} has a custom override; the user's version will NOT be touched."
    if status == "review_needed":
        return (
            f"{mid} has local edits to managed files "
            f"({len(record['files_with_local_edits'])}). Review before applying."
        )
    return f"{mid} status: {status}."


def preview_updates_rich(
    workspace_root: Path, module_id: str | None = None
) -> list[dict[str, Any]]:
    check = check_updates(workspace_root)
    modules = check["modules"]
    if module_id:
        modules = [m for m in modules if m["module_id"] == module_id]
    registry = load_template_registry()
    installed = discover_module_map(workspace_root, zone="source")

    rows: list[dict[str, Any]] = []
    for record in modules:
        mid = record["module_id"]
        template = registry.get(mid)
        location = installed.get(mid)
        files_to_replace: list[str] = []
        personal_touched: list[str] = []
        if template and location:
            relpaths = sorted(
                normalize_rel(path.relative_to(template.template_dir))
                for path in template.template_dir.rglob("*")
                if path.is_file()
            )
            for rel in relpaths:
                target_rel = normalize_rel(
                    (location.module_dir / rel).resolve().relative_to(workspace_root.resolve())
                )
                if _is_personal_path(target_rel):
                    personal_touched.append(target_rel)
                else:
                    files_to_replace.append(target_rel)

        risk = "low"
        if record["status"] == "custom_override_active":
            risk = "skipped"
        elif record["files_with_local_edits"]:
            risk = "medium"
        if personal_touched:
            risk = "high"

        recommended = "skip"
        if record["status"] == "update_available" and not record["files_with_local_edits"]:
            recommended = "apply"
        elif record["status"] == "review_needed":
            recommended = "review_local_edits_then_apply"
        elif record["status"] == "custom_override_active":
            recommended = "skip_custom_override"

        rows.append({
            "module_id": mid,
            "installed_version": record["installed_version"],
            "available_version": record["available_version"],
            "status": record["status"],
            "files_to_replace": files_to_replace,
            "files_with_local_edits": record["files_with_local_edits"],
            "personal_paths_touched": personal_touched,
            "risk_level": risk,
            "human_summary": _human_summary(record),
            "recommended_action": recommended,
        })
    return rows


def apply_updates_safe(
    workspace_root: Path,
    *,
    module_id: str | None = None,
    allow_local_edits: bool = False,
) -> ApplyResult:
    preview = preview_updates_rich(workspace_root, module_id=module_id)
    return perform_apply(workspace_root, preview, allow_local_edits=allow_local_edits)


__all__ = [
    "PERSONAL_PATH_PREFIXES",
    "ApplyResult",
    "apply_updates_safe",
    "check_updates",
    "preview_updates_rich",
    "rollback_update",
]
