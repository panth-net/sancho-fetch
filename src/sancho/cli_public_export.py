"""Shared helpers for writing public working output from CLI and MCP paths."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sancho.config import load_workspace_config
from sancho.project_export import PublicExportResult, export_records_to_public_outputs


def resolve_public_project_root(workspace_root: Path) -> Path:
    """Where the public working output should be written.

    1. CWD outside the Sancho repo  -> CWD.
    2. CWD inside the Sancho repo    -> the repo root.
    3. Never inside sancho-workspace -> the repo root.
    """
    cwd = Path.cwd().resolve()
    workspace = workspace_root.resolve()
    repo_root = workspace.parent
    try:
        cwd.relative_to(workspace)
        return repo_root
    except ValueError:
        pass
    try:
        cwd.relative_to(repo_root)
        return repo_root
    except ValueError:
        return cwd


def _exports_enabled(config: dict[str, Any]) -> bool:
    exports_cfg = config.get("exports", {}) if isinstance(config, dict) else {}
    return bool(exports_cfg.get("public_working_copy_enabled", True))


def _reusable_export(
    workspace_root: Path,
    record_dirs: list[Path],
    unit_sources: list[str] | None,
    project_root: Path,
) -> PublicExportResult | None:
    """Previous export for these exact records, if nothing changed.

    A pure cache-hit re-run used to rewrite an identical timestamped working
    file every time. When every unit was reused from cache, point back at the
    last export of the same record dirs instead -- provided it was written into
    the same project and all its files still exist.
    """
    if not unit_sources or any(source != "reused_cache" for source in unit_sources):
        return None
    from sancho.run_log import LOGS_DIRNAME, RUNS_LOG

    runs_log = workspace_root / LOGS_DIRNAME / RUNS_LOG
    if not runs_log.exists():
        return None
    import json

    wanted = sorted(str(Path(r)) for r in record_dirs)
    for line in reversed(runs_log.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") != "public_output_exported":
            continue
        detail = event.get("detail") or {}
        if sorted(detail.get("canonical_record_dirs") or []) != wanted:
            continue
        primary = Path(str(detail.get("primary_output_path") or ""))
        outputs = [Path(p) for p in detail.get("output_paths") or []]
        if not primary.name or not primary.exists():
            return None
        if any(not p.exists() for p in outputs):
            return None
        try:
            primary.relative_to(project_root)
        except ValueError:
            return None
        return PublicExportResult(
            primary_path=primary,
            output_paths=outputs,
            export_root=primary if primary.is_dir() else primary.parent,
            mode=str(detail.get("mode") or "single_file"),
            reused_count=len(record_dirs),
            canonical_record_dirs=[Path(r) for r in record_dirs],
        )
    return None


def auto_public_export(
    workspace_root: Path,
    record_dirs: list[Path],
    *,
    module_id: str = "",
    labels: list[str] | None = None,
    unit_sources: list[str] | None = None,
    quiet: bool = False,
) -> PublicExportResult | None:
    """Create the public working output for the given record(s) and log events."""
    from sancho.run_log import record_run_event

    record_dirs = [Path(r) for r in record_dirs if r]
    if not record_dirs:
        return None
    config = load_workspace_config(workspace_root)
    if not _exports_enabled(config):
        return None
    project_root = resolve_public_project_root(workspace_root)
    reusable = _reusable_export(workspace_root, record_dirs, unit_sources, project_root)
    if reusable is not None:
        return reusable
    try:
        result = export_records_to_public_outputs(
            record_dirs=record_dirs,
            project_root=project_root,
            workspace_root=workspace_root,
            labels=labels,
            config=config,
            unit_sources=unit_sources,
        )
    except Exception as exc:
        record_run_event(
            workspace_root,
            event_type="public_output_failed",
            module_id=module_id,
            detail={"project_root": str(project_root), "error_message": str(exc)},
        )
        if not quiet:
            print(f"[public-output] skipped: {exc}", file=sys.stderr)
        return None

    record_run_event(
        workspace_root,
        event_type="public_output_exported",
        module_id=module_id,
        detail={
            "primary_output_path": str(result.primary_path),
            "output_paths": [str(p) for p in result.output_paths],
            "mode": result.mode,
            "record_count": len(record_dirs),
            "canonical_record_dirs": [str(p) for p in result.canonical_record_dirs],
            "reused_units": result.reused_count,
            "fetched_units": result.fetched_count,
        },
    )
    return result


def print_primary(result: PublicExportResult | None, *, stream: Any = None) -> None:
    """Plain-text primary-path block + large-file notice."""
    if result is None:
        return
    out = stream if stream is not None else sys.stdout
    label = "Primary folder" if result.mode != "single_file" else "Primary file"
    print("", file=out)
    print(f"{label}:", file=out)
    print(str(result.primary_path), file=out)
    for big in result.large_files:
        size_mb = big.get("bytes", 0) / (1024 * 1024)
        print(
            f"\nHeads-up: {Path(big['path']).name} is {size_mb:.1f} MB. You now have your "
            f"own copy above. If you need disk space back later, it's safe to delete the "
            f"cached copy at {big.get('cached_path', '')}.",
            file=sys.stderr,
        )


def row_count(output: Any) -> int | None:
    if isinstance(output, dict):
        rows = output.get("rows")
        if isinstance(rows, list):
            return len(rows)
    if isinstance(output, list):
        return len(output)
    return None
