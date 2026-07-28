"""Live catalog discovery for Federal Register API v1.

Fetches:
  GET /agencies.json                          -> ~440 agencies (bare array)
  GET /documents/facets/{agencies|topics|sections|type|subtype}
                                              -> facet-keyed counts
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
    spec = importlib.util.spec_from_file_location("sancho_fedreg_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-federal-register-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=60, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
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
    if isinstance(data, list):
        count = len(data)
    elif isinstance(data, dict):
        count = len(data)
    else:
        count = 0
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": count,
        "error": "",
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.federal_register.documents"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    facets_base = str(getattr(BLUEPRINT, "FACETS_BASE", "/documents/facets"))
    facet_keys = list(getattr(BLUEPRINT, "FACET_KEYS", ["agencies", "topics", "sections", "type", "subtype"]))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    agencies, agencies_snap = _fetch_json(str(getattr(BLUEPRINT, "META_AGENCIES", "/agencies.json")))
    snapshots = [agencies_snap]

    facets: dict[str, Any] = {}
    for facet in facet_keys:
        data, snap = _fetch_json(f"{facets_base}/{facet}")
        snap["id"] = f"facet.{facet}"
        snapshots.append(snap)
        if snap.get("status") == "ok" and isinstance(data, dict):
            facets[facet] = data

    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"Federal Register catalog generation failed: {detail}")

    agencies_list = agencies if isinstance(agencies, list) else []

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "agencies": agencies_list,
        "facets": facets,
    }

    stats = {
        "family_count": len(families),
        "agency_count": len(agencies_list),
        "agencies_count": len(agencies_list),
        "facet_count": len(facets),
        "facets_count": len(facets),
    }
    # Add per-facet bucket counts for finer regression guard.
    for facet_name, facet_obj in facets.items():
        if isinstance(facet_obj, dict):
            stats[f"facet_{facet_name}_bucket_count"] = len(facet_obj)

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
        "agency_count": stats["agency_count"],
        "facet_count": stats["facet_count"],
    }
