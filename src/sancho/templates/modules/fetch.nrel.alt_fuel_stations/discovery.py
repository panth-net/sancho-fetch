"""Live catalog discovery for NREL Alt-Fuel Stations.

Fetches /v1.json with limit=1 to capture:
  - total_results count (~100k+)
  - field schema from a sample station
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
    spec = importlib.util.spec_from_file_location("sancho_nrel_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-nrel-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_sample() -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/v1.json"
    last_status = 0
    try:
        resp = requests.get(
            url,
            params={"api_key": os.getenv("DATA_GOV_API_KEY", "").strip(), "limit": 1},
            timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": "stations.sample",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    total = int(data.get("total_results", 0)) if isinstance(data, dict) else 0
    return data, {
        "id": "stations.sample",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.nrel.alt_fuel_stations"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    fuel_type_codes = list(getattr(BLUEPRINT, "FUEL_TYPE_CODES", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not os.getenv("DATA_GOV_API_KEY"):
        raise RuntimeError(f"{provider_id} requires DATA_GOV_API_KEY env var.")

    data, snap = _fetch_sample()
    snapshots = [snap]
    if snap.get("status") != "ok":
        raise RuntimeError(f"NREL catalog generation failed: {snap.get('error')}")

    stations = data.get("fuel_stations", []) if isinstance(data, dict) else []
    sample = stations[0] if stations and isinstance(stations[0], dict) else {}
    field_schema: dict[str, str] = {}
    for k, v in sample.items():
        if isinstance(v, bool):
            field_schema[k] = "bool"
        elif isinstance(v, int):
            field_schema[k] = "int"
        elif isinstance(v, float):
            field_schema[k] = "float"
        elif isinstance(v, str):
            field_schema[k] = "string"
        elif isinstance(v, list):
            field_schema[k] = "list"
        elif isinstance(v, dict):
            field_schema[k] = "dict"
        else:
            field_schema[k] = "nullable"

    # Station counts by fuel type.
    station_counts: dict[str, Any] = data.get("station_counts", {}) if isinstance(data, dict) else {}

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "fuel_type_codes": [{"code": c, "description": d} for c, d in fuel_type_codes],
        "field_schema": field_schema,
        "station_counts": station_counts,
        "total_stations": snap.get("count", 0),
    }
    stats = {
        "family_count": len(families),
        "fuel_type_count": len(fuel_type_codes),
        "fuel_types_count": len(fuel_type_codes),
        "field_count": len(field_schema),
        "fields_count": len(field_schema),
        "total_stations": snap.get("count", 0),
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
        "total_stations": stats["total_stations"],
        "field_count": stats["field_count"],
    }
