"""Cache catalog helpers: ``_catalog/`` index files for fetched-data.

Keeps an append-only ``cache-index.jsonl`` plus regenerated
``fetched-data-index.md`` / ``.csv`` so users and AI agents can inspect
what's cached without trusting an opaque flag.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIRNAME = "_catalog"
CACHE_INDEX_JSONL = "cache-index.jsonl"
INDEX_MD = "fetched-data-index.md"
INDEX_CSV = "fetched-data-index.csv"

DATA_FILE = "data.json"
PROVENANCE_FILE = "provenance.yml"
REQUEST_FILE = "request.yml"
HASH_FILE = "content.sha256"
README_FILE = "README.md"


def catalog_dir(data_raw_path: Path) -> Path:
    return Path(data_raw_path) / CATALOG_DIRNAME


def append_jsonl_event(target_catalog_dir: Path, event: dict[str, Any]) -> None:
    target_catalog_dir.mkdir(parents=True, exist_ok=True)
    path = target_catalog_dir / CACHE_INDEX_JSONL
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, default=str) + "\n")


def _read_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _record_summary(record_dir: Path) -> dict[str, Any] | None:
    prov = record_dir / PROVENANCE_FILE
    if not prov.exists():
        return None
    try:
        meta = _read_yaml(prov)
    except Exception:
        return None
    data_path = record_dir / DATA_FILE
    data_bytes = data_path.stat().st_size if data_path.exists() else 0
    return {
        "module_id": meta.get("module_id", ""),
        "family": meta.get("family", ""),
        "request_key": meta.get("request_key", ""),
        "timestamp": record_dir.name,
        "fetched_at": meta.get("fetched_at", ""),
        "source_url": meta.get("source_url", ""),
        "content_sha256": meta.get("content_sha256", ""),
        "data_bytes": data_bytes,
        "record_id": meta.get("record_id", ""),
        "record_dir": str(record_dir),
    }


def iter_cache_records(data_raw_path: Path) -> list[dict[str, Any]]:
    """Scan fetched-data and yield one row per cached record."""
    root = Path(data_raw_path)
    out: list[dict[str, Any]] = []
    if not root.exists():
        return out
    for module_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name != CATALOG_DIRNAME):
        for family_dir in sorted(p for p in module_dir.iterdir() if p.is_dir()):
            for key_dir in sorted(p for p in family_dir.iterdir() if p.is_dir()):
                for ts_dir in sorted(p for p in key_dir.iterdir() if p.is_dir()):
                    row = _record_summary(ts_dir)
                    if row is not None:
                        out.append(row)
    return out


def regenerate_indexes(data_raw_path: Path) -> None:
    """Rebuild fetched-data-index.md/csv from the on-disk catalog of records."""
    cdir = catalog_dir(data_raw_path)
    cdir.mkdir(parents=True, exist_ok=True)
    rows = iter_cache_records(Path(data_raw_path))
    rows.sort(key=lambda r: r.get("fetched_at", ""), reverse=True)

    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow([
        "module_id",
        "family",
        "request_key",
        "timestamp",
        "fetched_at",
        "source_url",
        "content_sha256",
        "data_bytes",
        "record_id",
    ])
    for r in rows:
        writer.writerow([
            r.get("module_id", ""),
            r.get("family", ""),
            r.get("request_key", ""),
            r.get("timestamp", ""),
            r.get("fetched_at", ""),
            r.get("source_url", ""),
            r.get("content_sha256", ""),
            r.get("data_bytes", ""),
            r.get("record_id", ""),
        ])
    (cdir / INDEX_CSV).write_text(csv_buf.getvalue(), encoding="utf-8")

    lines = [
        "# Fetched-data index",
        "",
        f"Total records: **{len(rows)}**.",
        "",
        "| Module | Family | Request key | Fetched at | Bytes | Record id |",
        "|---|---|---|---|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r.get('module_id', '')}` "
            f"| `{r.get('family', '')}` "
            f"| `{r.get('request_key', '')}` "
            f"| {r.get('fetched_at', '')} "
            f"| {r.get('data_bytes', 0)} "
            f"| `{r.get('record_id', '')}` |"
        )
    lines.append("")
    (cdir / INDEX_MD).write_text("\n".join(lines), encoding="utf-8")


def render_readme(
    *,
    module_id: str,
    family: str,
    request_key: str,
    fetched_at_iso: str,
    source_url: str,
    params: dict[str, Any],
    content_sha256: str,
    data_bytes: int,
    record_id: str,
) -> str:
    params_block = (
        json.dumps(params, indent=2, default=str, sort_keys=True) if params else "{}"
    )
    return (
        f"# {module_id} - {family} - {request_key}\n"
        f"\n"
        f"Cached fetched-data record.\n"
        f"\n"
        f"- record_id: `{record_id}`\n"
        f"- fetched_at: `{fetched_at_iso}`\n"
        f"- source_url: {source_url or '(unspecified)'}\n"
        f"- content_sha256: `{content_sha256}`\n"
        f"- data_bytes: {data_bytes}\n"
        f"\n"
        f"## Request params\n"
        f"\n"
        f"```json\n{params_block}\n```\n"
        f"\n"
        f"## Provenance\n"
        f"\n"
        f"See `provenance.yml` for full machine-readable provenance.\n"
        f"See `request.yml` for the exact request that produced this record.\n"
    )
