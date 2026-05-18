"""Build a ``sancho-fetched-data/`` project bundle from a cache record.

A bundle lives in the user's working folder (not in the canonical Sancho Fetch
library) and contains everything a non-Sancho-aware downstream tool needs::

    Some Project/
      sancho-fetched-data/
        2026-05-11-fetch.world_bank-7a8c1f2b3d4e/
          README.md
          manifest.yml
          data.json                # always (small/medium)
          data.csv                  # generated when payload is tabular
          provenance.yml            # copied from cache
          source-cache-links.yml    # paths back to canonical fetched-data record(s)

Large records (>``LARGE_BUNDLE_BYTES``) get a *pointer bundle* instead of a
copy: README, manifest, sample rows, source links, and instructions. Canonical
data stays in ``fetched-data/`` either way.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PROJECT_FOLDER = "sancho-fetched-data"
LARGE_BUNDLE_BYTES = 25 * 1024 * 1024  # 25 MB -- bigger than this becomes a pointer bundle
SAMPLE_ROW_COUNT = 50


@dataclass
class ExportResult:
    bundle_dir: Path
    mode: str  # "copy" | "pointer"
    record_dirs: list[Path]
    skipped: list[str]
    bytes_written: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date_segment() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()) or "bundle"
    return cleaned.strip("-._")[:120] or "bundle"


def _bundle_dir_name(record_id: str, label: str | None) -> str:
    parts = [_date_segment()]
    if label:
        parts.append(_slugify(label))
    else:
        parts.append(_slugify(record_id))
    return "-".join(parts)


def _read_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: Any) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _is_tabular(payload: Any) -> tuple[bool, list[dict[str, Any]]]:
    if isinstance(payload, list) and payload and all(isinstance(row, dict) for row in payload):
        return True, payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "results", "records", "items"):
            value = payload.get(key)
            if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
                return True, value
    return False, []


def _render_csv(rows: list[dict[str, Any]]) -> str:
    # Stable column order: union of keys, preserving first-seen.
    seen: list[str] = []
    seen_set: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen_set:
                seen.append(key)
                seen_set.add(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=seen, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _stringify(row.get(k)) for k in seen})
    return buf.getvalue()


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, default=str)


def _render_manifest(
    *,
    record_dirs: list[Path],
    mode: str,
    bundle_dir: Path,
    label: str | None,
    workspace_root: Path,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for record_dir in record_dirs:
        prov = _read_yaml(record_dir / "provenance.yml")
        records.append({
            "record_id": prov.get("record_id", ""),
            "module_id": prov.get("module_id", ""),
            "family": prov.get("family", ""),
            "request_key": prov.get("request_key", ""),
            "fetched_at": prov.get("fetched_at", ""),
            "source_url": prov.get("source_url", ""),
            "content_sha256": prov.get("content_sha256", ""),
            "data_bytes": prov.get("data_bytes", 0),
            "canonical_record_dir": str(record_dir),
        })
    return {
        "bundle_id": bundle_dir.name,
        "label": label or "",
        "created_at": _now_iso(),
        "mode": mode,
        "sancho_workspace": str(workspace_root),
        "record_count": len(records),
        "records": records,
    }


def _render_source_cache_links(record_dirs: list[Path], workspace_root: Path) -> dict[str, Any]:
    """Pointers back to canonical fetched-data records."""
    return {
        "workspace_root": str(workspace_root),
        "records": [
            {
                "record_dir": str(record_dir),
                "data_file": str(record_dir / "data.json"),
                "provenance_file": str(record_dir / "provenance.yml"),
                "request_file": str(record_dir / "request.yml"),
            }
            for record_dir in record_dirs
        ],
    }


def _render_readme(
    *,
    bundle_dir: Path,
    mode: str,
    record_dirs: list[Path],
    label: str | None,
    sample_rows: int,
) -> str:
    head = [
        f"# {bundle_dir.name}",
        "",
        "sancho-fetched-data bundle.",
        "",
        f"- Created at: {_now_iso()}",
        f"- Mode: **{mode}**" + (" -- small/medium payload copied in full." if mode == "copy" else " -- pointer bundle (large payload kept in Sancho Fetch)."),
        f"- Records included: {len(record_dirs)}",
    ]
    if label:
        head.append(f"- Label: {label}")
    head.append("")
    head.append("## What's in this folder")
    head.append("")
    if mode == "copy":
        head.append("- `data.json` -- full payload from the cache.")
        head.append("- `data.csv` -- generated when the payload is tabular (a list of dicts).")
    else:
        head.append(f"- `data.sample.json` -- first {sample_rows} rows of the canonical payload.")
        head.append("- Full data stays in `source-cache-links.yml -> data_file` to avoid filling your drive.")
    head.append("- `manifest.yml` -- machine-readable summary of every record in this bundle.")
    head.append("- `provenance.yml` -- copied from the canonical cache record.")
    head.append("- `source-cache-links.yml` -- absolute paths back to the canonical Sancho Fetch records.")
    head.append("")
    head.append("## Re-use vs re-fetch")
    head.append("")
    head.append("- **Re-used:** every record listed here was loaded from the existing cache. No upstream calls were made for this export.")
    head.append("- **Re-fetch:** run the original sancho command again to refresh the canonical record. This bundle does not mutate the cache.")
    head.append("")
    head.append("## Canonical records")
    head.append("")
    for record_dir in record_dirs:
        head.append(f"- `{record_dir}`")
    head.append("")
    return "\n".join(head)


def _bundle_record(
    *, record_dir: Path, bundle_dir: Path, mode: str
) -> tuple[int, list[str]]:
    """Copy or sample one record into the bundle. Returns (bytes_written, files_added)."""
    files: list[str] = []
    bytes_written = 0
    data_path = record_dir / "data.json"
    if not data_path.exists():
        return bytes_written, files

    if mode == "copy":
        dst = bundle_dir / "data.json"
        shutil.copy2(data_path, dst)
        bytes_written += dst.stat().st_size
        files.append(dst.name)
        try:
            payload = _read_json(data_path)
        except Exception:
            payload = None
        if payload is not None:
            tabular, rows = _is_tabular(payload)
            if tabular:
                csv_path = bundle_dir / "data.csv"
                csv_text = _render_csv(rows)
                csv_path.write_text(csv_text, encoding="utf-8")
                bytes_written += csv_path.stat().st_size
                files.append(csv_path.name)
    else:
        try:
            payload = _read_json(data_path)
        except Exception:
            payload = None
        sample: Any = payload
        if isinstance(payload, list):
            sample = payload[:SAMPLE_ROW_COUNT]
        elif isinstance(payload, dict):
            tabular, rows = _is_tabular(payload)
            if tabular:
                sample = {"_sampled_from": "data.json", "rows": rows[:SAMPLE_ROW_COUNT]}
        sample_path = bundle_dir / "data.sample.json"
        sample_path.write_text(json.dumps(sample, indent=2, default=str), encoding="utf-8")
        bytes_written += sample_path.stat().st_size
        files.append(sample_path.name)

    prov_src = record_dir / "provenance.yml"
    if prov_src.exists():
        dst = bundle_dir / "provenance.yml"
        shutil.copy2(prov_src, dst)
        bytes_written += dst.stat().st_size
        files.append(dst.name)

    req_src = record_dir / "request.yml"
    if req_src.exists():
        dst = bundle_dir / "request.yml"
        shutil.copy2(req_src, dst)
        bytes_written += dst.stat().st_size
        files.append(dst.name)
    return bytes_written, files


def export_record_to_project(
    *,
    record_dir: Path,
    project_root: Path,
    workspace_root: Path,
    label: str | None = None,
) -> ExportResult:
    """Create a sancho-fetched-data bundle for one cache record."""
    record_dir = Path(record_dir)
    if not record_dir.exists():
        raise FileNotFoundError(f"Cache record dir does not exist: {record_dir}")
    project_root = Path(project_root)
    project_root.mkdir(parents=True, exist_ok=True)

    bundles_root = project_root / PROJECT_FOLDER
    bundles_root.mkdir(parents=True, exist_ok=True)

    prov = _read_yaml(record_dir / "provenance.yml")
    record_id = str(prov.get("record_id") or record_dir.name)
    data_path = record_dir / "data.json"
    data_bytes = data_path.stat().st_size if data_path.exists() else 0
    mode = "pointer" if data_bytes > LARGE_BUNDLE_BYTES else "copy"

    bundle_dir = bundles_root / _bundle_dir_name(record_id, label)
    counter = 1
    while bundle_dir.exists():
        bundle_dir = bundles_root / f"{_bundle_dir_name(record_id, label)}_{counter}"
        counter += 1
    bundle_dir.mkdir(parents=True, exist_ok=True)

    record_dirs = [record_dir]
    bytes_written, _ = _bundle_record(
        record_dir=record_dir, bundle_dir=bundle_dir, mode=mode
    )

    _write_yaml(
        bundle_dir / "manifest.yml",
        _render_manifest(
            record_dirs=record_dirs,
            mode=mode,
            bundle_dir=bundle_dir,
            label=label,
            workspace_root=workspace_root,
        ),
    )
    _write_yaml(
        bundle_dir / "source-cache-links.yml",
        _render_source_cache_links(record_dirs, workspace_root),
    )
    (bundle_dir / "README.md").write_text(
        _render_readme(
            bundle_dir=bundle_dir,
            mode=mode,
            record_dirs=record_dirs,
            label=label,
            sample_rows=SAMPLE_ROW_COUNT,
        ),
        encoding="utf-8",
    )

    return ExportResult(
        bundle_dir=bundle_dir,
        mode=mode,
        record_dirs=record_dirs,
        skipped=[],
        bytes_written=bytes_written,
    )
