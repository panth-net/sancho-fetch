"""Live catalog discovery for OpenFEMA.

Crawls two metadata endpoints:
  GET /api/open/v1/OpenFemaDataSets        -> 47+ datasets with titles, versions, counts
  GET /api/open/v1/OpenFemaDataSetFields   -> column schema for every dataset

Merges them so catalog.json contains each dataset alongside its fields.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_fema_catalog_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BLUEPRINT = _load_blueprint()

_USER_AGENT = "sancho-fema-discovery/1.0"
_PAGE_SIZE = 1000  # OpenFEMA maximum per request


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_paginated(path: str, envelope_key: str) -> tuple[list[Any], dict[str, Any]]:
    """Walk an OpenFEMA endpoint paginating via $skip/$top.

    Returns (rows, snapshot) where snapshot describes the HTTP result so the
    meta file can record provenance for every source we touched.
    """
    base_url = str(getattr(BLUEPRINT, "BASE_URL", "https://www.fema.gov/api/open"))
    url = f"{base_url.rstrip('/')}{path}"
    rows: list[Any] = []
    skip = 0
    last_status = 0
    try:
        while True:
            params = {"$top": _PAGE_SIZE, "$skip": skip, "$format": "json"}
            resp = requests.get(
                url, params=params, timeout=60, headers={"User-Agent": _USER_AGENT},
            )
            last_status = resp.status_code
            resp.raise_for_status()
            payload = resp.json()
            page = payload.get(envelope_key) if isinstance(payload, dict) else None
            if not isinstance(page, list) or not page:
                break
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            skip += _PAGE_SIZE
    except Exception as exc:
        return rows, {
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": len(rows),
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    return rows, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(rows),
        "error": "",
        "fetched_at": _now_iso(),
    }


def _index_fields_by_dataset(field_rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """Group /OpenFemaDataSetFields rows by their parent dataset.

    Every field row has an "openFemaDataSet" key naming the dataset it belongs
    to. We return {dataset_name: [field_dict, ...]} keeping only the subset of
    attributes useful for callers (name, type, description, primary key flag).
    """
    by_dataset: dict[str, list[dict[str, Any]]] = {}
    for row in field_rows:
        if not isinstance(row, dict):
            continue
        dataset_name = row.get("openFemaDataSet") or row.get("dataset")
        if not dataset_name:
            continue
        entry = {
            "name": row.get("name"),
            "title": row.get("title"),
            "type": row.get("type"),
            "description": row.get("description"),
            "primaryKey": row.get("primaryKey"),
            "deprecated": row.get("deprecated"),
            "deprecatedInAPIVersion": row.get("deprecatedInAPIVersion"),
            "addedInAPIVersion": row.get("addedInAPIVersion"),
        }
        by_dataset.setdefault(dataset_name, []).append(entry)
    return by_dataset


def _build_datasets_index(
    dataset_rows: list[Any],
    field_map: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge dataset metadata + field schema into one list of dataset dicts."""
    out: list[dict[str, Any]] = []
    for row in dataset_rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        entry = {
            "identifier": row.get("identifier"),
            "name": name,
            "title": row.get("title"),
            "description": row.get("description"),
            "version": row.get("version"),
            "webService": row.get("webService"),
            "dataDictionary": row.get("dataDictionary"),
            "recordCount": row.get("recordCount"),
            "distribution": row.get("distribution"),
            "accrualPeriodicity": row.get("accrualPeriodicity"),
            "modified": row.get("modified"),
            "lastDataSetRefresh": row.get("lastDataSetRefresh"),
            "temporal": row.get("temporal"),
            "theme": row.get("theme"),
            "keyword": row.get("keyword"),
            "fields": field_map.get(name, []),
        }
        out.append(entry)
    return out


def _write_catalog_files(
    module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any],
) -> None:
    (module_dir / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )
    (module_dir / "catalog.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.fema.openfema"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    docs_query_params = str(getattr(BLUEPRINT, "DOCS_QUERY_PARAMS", ""))
    meta_datasets_path = str(getattr(BLUEPRINT, "META_DATASETS", "/v1/OpenFemaDataSets"))
    meta_fields_path = str(getattr(BLUEPRINT, "META_FIELDS", "/v1/OpenFemaDataSetFields"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    dataset_rows, datasets_snapshot = _fetch_paginated(meta_datasets_path, "OpenFemaDataSets")
    field_rows, fields_snapshot = _fetch_paginated(meta_fields_path, "OpenFemaDataSetFields")

    snapshots = [datasets_snapshot, fields_snapshot]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"OpenFEMA live catalog generation failed: {detail}")

    field_map = _index_fields_by_dataset(field_rows)
    datasets = _build_datasets_index(dataset_rows, field_map)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "datasets": datasets,
    }

    # Aggregate stat keys (both singular and plural for consistency with
    # other providers' meta files).
    total_field_count = sum(len(v) for v in field_map.values())
    stats = {
        "family_count": len(families),
        "dataset_count": len(datasets),
        "datasets_count": len(datasets),
        "field_count": total_field_count,
        "fields_count": total_field_count,
        "total_record_count": sum(
            int(d.get("recordCount") or 0) for d in datasets
        ),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [docs_url, docs_query_params],
        },
    }

    _write_catalog_files(module_dir, catalog, meta)
    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "catalog": str(module_dir / "catalog.json"),
        "catalog_meta": str(module_dir / "catalog.meta.json"),
        "family_count": stats["family_count"],
        "dataset_count": stats["dataset_count"],
        "field_count": stats["field_count"],
    }
