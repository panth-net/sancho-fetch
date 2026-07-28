"""Live catalog discovery for USDA FoodData Central.

FDC doesn't expose a discovery endpoint enumerating every category / nutrient,
so we capture:
  - total food count (via /foods/search pagination meta)
  - per-dataType counts (one search per dataType)
  - field schema from a sample response
  - the 5 known dataTypes (Branded, Foundation, Survey, SR Legacy, Experimental)
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_fdc_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-fdc-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key() -> str:
    return os.getenv("DATA_GOV_API_KEY", "").strip()


def _fetch(path: str, *, params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    merged = {"api_key": _key(), **params}
    last_status = 0
    try:
        resp = requests.get(
            url, params=merged, timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": path + ":" + str(params.get("dataType", "all")),
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    total = 0
    if isinstance(data, dict):
        total = int(data.get("totalHits", 0)) if isinstance(data.get("totalHits"), int) else 0
    return data, {
        "id": path + ":" + str(params.get("dataType", "all")),
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _extract_sample_schema(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    foods = data.get("foods")
    if not isinstance(foods, list) or not foods:
        return {}
    sample = foods[0]
    if not isinstance(sample, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in sample.items():
        if isinstance(v, bool):
            out[k] = "bool"
        elif isinstance(v, int):
            out[k] = "int"
        elif isinstance(v, float):
            out[k] = "float"
        elif isinstance(v, str):
            out[k] = "string"
        elif isinstance(v, list):
            out[k] = "list"
        elif isinstance(v, dict):
            out[k] = "dict"
        else:
            out[k] = "nullable"
    return out


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.usda.fooddata_search"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    data_types = list(getattr(BLUEPRINT, "DATA_TYPES", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _key():
        raise RuntimeError(f"{provider_id} requires DATA_GOV_API_KEY env var.")

    # Overall count + schema from an unfiltered search.
    all_data, all_snap = _fetch("/foods/search", params={"query": "*", "pageSize": 1})
    snapshots = [all_snap]
    total_hits = all_snap.get("count") or 0
    schema = _extract_sample_schema(all_data) if all_snap.get("status") == "ok" else {}

    # Per-dataType count.
    per_type: dict[str, int] = {}
    for dt in data_types:
        _, snap = _fetch("/foods/search", params={"query": "*", "pageSize": 1, "dataType": dt})
        snapshots.append(snap)
        if snap.get("status") == "ok":
            per_type[dt] = snap.get("count", 0)

    if not schema:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots)
        raise RuntimeError(f"FDC catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "data_types": data_types,
        "per_data_type_count": per_type,
        "total_food_count": total_hits,
        "field_schema": schema,
    }
    stats = {
        "family_count": len(families),
        "data_type_count": len(data_types),
        "data_types_count": len(data_types),
        "field_count": len(schema),
        "fields_count": len(schema),
        "total_food_count": total_hits,
        "per_type_total": sum(per_type.values()),
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
        "data_type_count": stats["data_type_count"],
        "field_count": stats["field_count"],
        "total_food_count": stats["total_food_count"],
    }
