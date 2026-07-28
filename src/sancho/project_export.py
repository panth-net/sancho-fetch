"""Public working output: turn cache record(s) into the file(s) a user opens.

Two layers:

* The canonical cache (``sancho-workspace/fetched-data/...``) is faithful: it
  stores the original downloaded file byte-for-byte when one exists, plus the
  parsed ``data.json``.
* The *public working output* (``sancho-downloads/...``) is the file the user
  actually opens. It favors familiar/openable formats but never converts at the
  cost of losing information.

The format ladder and writers live in :mod:`sancho.public_output`; this module
orchestrates them across one or more records and applies the single-vs-multiple
layout rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sancho.public_output import (
    DEFAULT_LARGE_FILE_BYTES,
    choose_public_outputs,
    label_for,
    read_json,
    read_yaml,
    timestamp,
    write_plan,
)

PROJECT_FOLDER = "sancho-downloads"


@dataclass
class PublicExportResult:
    primary_path: Path
    output_paths: list[Path]
    export_root: Path
    mode: str  # "single_file" | "single_dataset_folder" | "multi_dataset_folder"
    reused_count: int = 0
    fetched_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    canonical_record_dirs: list[Path] = field(default_factory=list)
    large_files: list[dict[str, Any]] = field(default_factory=list)


def _counts(unit_sources: list[str] | None) -> tuple[int, int, int, int]:
    reused = fetched = skipped = failed = 0
    for source in (unit_sources or []):
        if source == "reused_cache":
            reused += 1
        elif source == "fetched_api":
            fetched += 1
        elif source == "skipped":
            skipped += 1
        elif source == "failed":
            failed += 1
    return reused, fetched, skipped, failed


def export_records_to_public_outputs(
    *,
    record_dirs: list[Path],
    project_root: Path,
    workspace_root: Path,
    labels: list[str] | None = None,
    request_label: str | None = None,
    config: dict[str, Any] | None = None,
    unit_sources: list[str] | None = None,
    now: datetime | None = None,
) -> PublicExportResult:
    """Export one or more cache records into the project's public folder.

    ``unit_sources`` (parallel to ``record_dirs``) carries per-unit cache status
    (``"reused_cache"`` / ``"fetched_api"`` / ...) so counts are accurate.
    """
    requested = [Path(r) for r in record_dirs]
    if not requested:
        raise ValueError("export_records_to_public_outputs requires at least one record dir")
    # Skip missing records rather than aborting the whole batch -- one bad dir
    # must not lose the good ones. Keep unit_sources aligned to survivors.
    record_dirs = []
    kept_sources: list[str] = []
    for index, record_dir in enumerate(requested):
        if record_dir.exists():
            record_dirs.append(record_dir)
            if unit_sources and index < len(unit_sources):
                kept_sources.append(unit_sources[index])
        # else: silently dropped here; caller logs/Reports the miss.
    if not record_dirs:
        raise FileNotFoundError(
            f"None of the {len(requested)} requested cache record dir(s) exist: {requested[0]} ..."
        )
    if unit_sources is not None:
        unit_sources = kept_sources or unit_sources

    exports_cfg = (config or {}).get("exports", {}) if isinstance(config, dict) else {}
    folder_name = str(exports_cfg.get("public_folder_name") or PROJECT_FOLDER)
    prefer_csv = bool(exports_cfg.get("prefer_csv_when_lossless", True))
    keep_original = bool(exports_cfg.get("keep_original_alongside_conversion", True))
    unzip_archives = bool(exports_cfg.get("unzip_archives", True))
    # "xlsx" (default): Excel-safe tables -- string codes like "01003" stay
    # text, no locale/separator guessing. Set to "csv" for raw CSV output.
    tabular_format = str(exports_cfg.get("tabular_format") or "xlsx").lower()
    large_file_bytes = int(exports_cfg.get("large_file_warn_bytes", DEFAULT_LARGE_FILE_BYTES))

    export_root = Path(project_root) / folder_name
    export_root.mkdir(parents=True, exist_ok=True)

    per_record: list[tuple[Path, str, list]] = []
    for index, record_dir in enumerate(record_dirs):
        provenance = read_yaml(record_dir / "provenance.yml")
        try:
            payload = read_json(record_dir / "data.json")
        except Exception:
            payload = None
        override = labels[index] if labels and index < len(labels) else None
        label = label_for(provenance, record_dir, override)
        plans = choose_public_outputs(
            record_dir, payload, provenance, label,
            prefer_csv=prefer_csv,
            keep_original_alongside=keep_original,
            unzip_archives=unzip_archives,
            tabular_format=tabular_format,
        )
        per_record.append((record_dir, label, plans))

    stamp = timestamp(now)
    output_paths: list[Path] = []
    large_files: list[dict[str, Any]] = []

    single_record = len(per_record) == 1
    single_flat = (
        single_record
        and len(per_record[0][2]) == 1
        and per_record[0][2][0].kind != "unzip"
    )

    if single_flat:
        record_dir, label, plans = per_record[0]
        taken: set[str] = set()
        written = write_plan(
            plans[0], record_dir, export_root, f"{stamp}_{label}",
            taken, large_file_bytes, large_files,
        )
        output_paths.extend(written)
        primary = written[0] if written else export_root
        mode = "single_file"
    elif single_record:
        record_dir, label, plans = per_record[0]
        folder = export_root / f"{stamp}_{label}"
        folder.mkdir(parents=True, exist_ok=True)
        taken = set()
        for plan in plans:
            output_paths.extend(
                write_plan(plan, record_dir, folder, label, taken, large_file_bytes, large_files)
            )
        primary = folder
        mode = "single_dataset_folder"
    else:
        folder = export_root / stamp
        folder.mkdir(parents=True, exist_ok=True)
        taken = set()
        for record_dir, label, plans in per_record:
            for plan in plans:
                output_paths.extend(
                    write_plan(plan, record_dir, folder, label, taken, large_file_bytes, large_files)
                )
        primary = folder
        mode = "multi_dataset_folder"

    reused, fetched, skipped, failed = _counts(unit_sources)
    return PublicExportResult(
        primary_path=primary,
        output_paths=output_paths,
        export_root=export_root,
        mode=mode,
        reused_count=reused,
        fetched_count=fetched,
        skipped_count=skipped,
        failed_count=failed,
        canonical_record_dirs=list(record_dirs),
        large_files=large_files,
    )


__all__ = [
    "PROJECT_FOLDER",
    "PublicExportResult",
    "export_records_to_public_outputs",
]
