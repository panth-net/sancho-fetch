"""Live catalog discovery for CFPB Consumer Complaint Database.

Fetches the search endpoint with size=1 to capture:
  - Total record count (14.5M+)
  - All 12 aggregation facets with their full bucket lists
    (product, issue, state, company, etc. -- each is a categorical value
     that can be used to filter queries)
  - The 19-field _source schema
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
    spec = importlib.util.spec_from_file_location("sancho_cfpb_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "Mozilla/5.0 sancho-cfpb-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_aggregations() -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/"
    last_status = 0
    try:
        resp = requests.get(
            url, params={"size": 1}, timeout=90,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": "aggregations",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    total = 0
    if isinstance(data, dict):
        hits = data.get("hits", {})
        if isinstance(hits, dict):
            total_obj = hits.get("total", {})
            if isinstance(total_obj, dict):
                total = int(total_obj.get("value", 0))
            elif isinstance(total_obj, int):
                total = total_obj
    return data, {
        "id": "aggregations",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _simplify_aggregation(agg: dict[str, Any]) -> dict[str, Any]:
    """Extract buckets from an Elasticsearch agg response."""
    # Nested structure: agg -> agg.<field> -> buckets
    for k, v in agg.items():
        if isinstance(v, dict) and isinstance(v.get("buckets"), list):
            return {
                "bucket_count": len(v["buckets"]),
                "buckets": [
                    {"key": b.get("key_as_string") or b.get("key"), "doc_count": b.get("doc_count")}
                    for b in v["buckets"] if isinstance(b, dict)
                ],
            }
    return {"bucket_count": 0, "buckets": []}


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.cfpb.complaints"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    data, snap = _fetch_aggregations()
    snapshots = [snap]
    if snap.get("status") != "ok":
        raise RuntimeError(f"CFPB catalog generation failed: {snap.get('error')}")

    aggs_raw = data.get("aggregations", {}) if isinstance(data, dict) else {}
    aggregations: dict[str, Any] = {}
    for name, agg in aggs_raw.items():
        if not isinstance(agg, dict):
            continue
        aggregations[name] = _simplify_aggregation(agg)

    # Sample row schema.
    hits = data.get("hits", {}).get("hits", []) if isinstance(data, dict) else []
    sample_source = hits[0].get("_source", {}) if hits and isinstance(hits[0], dict) else {}
    field_schema: dict[str, str] = {}
    for k, v in (sample_source.items() if isinstance(sample_source, dict) else []):
        if isinstance(v, bool):
            field_schema[k] = "bool"
        elif isinstance(v, int):
            field_schema[k] = "int"
        elif isinstance(v, float):
            field_schema[k] = "float"
        elif isinstance(v, str):
            field_schema[k] = "string"
        elif v is None:
            field_schema[k] = "nullable"
        else:
            field_schema[k] = type(v).__name__

    total_complaints = snap.get("count", 0)
    total_buckets = sum(a.get("bucket_count", 0) for a in aggregations.values())

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "aggregations": aggregations,
        "field_schema": field_schema,
        "total_complaints": total_complaints,
    }
    stats = {
        "family_count": len(families),
        "aggregation_count": len(aggregations),
        "aggregations_count": len(aggregations),
        "total_bucket_count": total_buckets,
        "field_count": len(field_schema),
        "fields_count": len(field_schema),
        "total_complaints": total_complaints,
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [docs_url],
        },
    }

    (module_dir / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )
    (module_dir / "catalog.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )

    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "family_count": stats["family_count"],
        "aggregation_count": stats["aggregation_count"],
        "total_bucket_count": stats["total_bucket_count"],
        "total_complaints": stats["total_complaints"],
    }
