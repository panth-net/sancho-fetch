"""Live catalog discovery for NHTSA (vPIC + api.nhtsa.gov).

Fetches the two canonical vPIC discovery endpoints:

  GET /vehicles/GetAllMakes?format=json           (~12,000 makes)
  GET /vehicles/GetVehicleVariableList?format=json (~144 vPIC variables)

Plus the first page of GetAllManufacturers (100 records) as a sample -- the full
manufacturer index is ~150 pages and can be enumerated via the family spec but
is not inlined to keep catalog size reasonable.
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
    spec = importlib.util.spec_from_file_location("sancho_nhtsa_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-nhtsa-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(base: str, path: str, *, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    url = f"{base.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, params=params, timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    results = data.get("Results") if isinstance(data, dict) else None
    count = len(results) if isinstance(results, list) else 0
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": count,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _extract_results(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        r = payload.get("Results")
        if isinstance(r, list):
            return r
    return []


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.nhtsa.recalls"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    base_vpic = str(getattr(BLUEPRINT, "BASE_URL_VPIC"))
    all_makes_path = str(getattr(BLUEPRINT, "VPIC_ALL_MAKES", "/vehicles/GetAllMakes"))
    variable_list_path = str(getattr(BLUEPRINT, "VPIC_VARIABLE_LIST", "/vehicles/GetVehicleVariableList"))
    manufacturers_path = str(getattr(BLUEPRINT, "VPIC_MANUFACTURERS", "/vehicles/GetAllManufacturers"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    makes_raw, makes_snap = _fetch_json(base_vpic, all_makes_path, params={"format": "json"})
    variables_raw, vars_snap = _fetch_json(base_vpic, variable_list_path, params={"format": "json"})
    manufacturers_raw, mfg_snap = _fetch_json(base_vpic, manufacturers_path, params={"format": "json", "page": 1})

    snapshots = [makes_snap, vars_snap, mfg_snap]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"NHTSA vPIC catalog generation failed: {detail}")

    makes = _extract_results(makes_raw)
    variables = _extract_results(variables_raw)
    manufacturers_page1 = _extract_results(manufacturers_raw)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "makes": makes,
        "vehicle_variables": variables,
        "manufacturers_sample": manufacturers_page1,
    }
    stats = {
        "family_count": len(families),
        "make_count": len(makes),
        "makes_count": len(makes),
        "variable_count": len(variables),
        "variables_count": len(variables),
        "manufacturers_sample_count": len(manufacturers_page1),
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
        "make_count": stats["make_count"],
        "variable_count": stats["variable_count"],
    }
