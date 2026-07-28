"""Live catalog discovery for BEA (Bureau of Economic Analysis).

Walks two metadata methods:
  GetDataSetList                    -> 13 datasets
  GetParameterList?DataSetName=X    -> ~4-10 parameters per dataset

Merges them so each dataset entry in catalog.json carries its parameter schema.
Requires BEA_API_KEY env var.
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
    spec = importlib.util.spec_from_file_location("sancho_bea_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-bea-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key() -> str:
    return os.getenv("BEA_API_KEY", "").strip()


def _fetch(params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    merged = {"UserID": _key(), "ResultFormat": "JSON", **params}
    last_status = 0
    try:
        resp = requests.get(
            base_url, params=merged, timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": params.get("method", "unknown") + ":" + str(params.get("DataSetName", "")),
            "url": base_url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    results = (data.get("BEAAPI", {}) or {}).get("Results", {}) if isinstance(data, dict) else {}
    return data, {
        "id": params.get("method", "unknown") + ":" + str(params.get("DataSetName", "")),
        "url": base_url,
        "status": "ok",
        "http_status": last_status,
        "count": len(results) if isinstance(results, dict) else 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _extract_list(data: Any, envelope_keys: list[str]) -> list[dict[str, Any]]:
    """BEA often returns either a list or a single dict under Results.X.

    The envelope key depends on the method -- Dataset / Parameter / ParamValue.
    """
    if not isinstance(data, dict):
        return []
    results = data.get("BEAAPI", {}).get("Results", {})
    if not isinstance(results, dict):
        return []
    for key in envelope_keys:
        v = results.get(key)
        if isinstance(v, list):
            return [item for item in v if isinstance(item, dict)]
        if isinstance(v, dict):
            return [v]
    return []


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.bea.nipa_table"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _key():
        raise RuntimeError(f"{provider_id} requires BEA_API_KEY env var.")

    dataset_data, ds_snap = _fetch({"method": "GetDataSetList"})
    snapshots = [ds_snap]
    if ds_snap.get("status") != "ok":
        raise RuntimeError(f"BEA GetDataSetList failed: {ds_snap.get('error')}")

    datasets = _extract_list(dataset_data, ["Dataset"])

    # For each dataset, fetch its parameter list.
    total_parameters = 0
    for ds in datasets:
        ds_name = ds.get("DatasetName") or ds.get("DataSetName")
        if not ds_name:
            ds["parameters"] = []
            continue
        p_data, p_snap = _fetch({"method": "GetParameterList", "DataSetName": ds_name})
        snapshots.append(p_snap)
        if p_snap.get("status") != "ok":
            ds["parameters"] = []
            continue
        params = _extract_list(p_data, ["Parameter"])
        ds["parameters"] = params
        total_parameters += len(params)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "datasets": datasets,
    }
    stats = {
        "family_count": len(families),
        "dataset_count": len(datasets),
        "datasets_count": len(datasets),
        "total_parameter_count": total_parameters,
        "datasets_with_parameters": sum(1 for d in datasets if d.get("parameters")),
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
        "dataset_count": stats["dataset_count"],
        "total_parameter_count": stats["total_parameter_count"],
    }
