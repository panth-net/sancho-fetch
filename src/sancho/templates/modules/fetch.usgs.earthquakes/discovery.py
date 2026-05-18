"""Live catalog discovery for USGS FDSN earthquakes.

Uses the single canonical metadata endpoint:
  GET /fdsnws/event/1/application.json
which returns everything in one shot: catalogs, contributors, product types,
event types, magnitude types, and the full parameter spec with types/ranges.
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
    spec = importlib.util.spec_from_file_location("sancho_usgs_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-usgs-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL", "https://earthquake.usgs.gov/fdsnws/event/1"))
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
    count = 0
    if isinstance(data, dict):
        count = sum(len(v) for v in data.values() if isinstance(v, list))
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": count,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _fetch_text(path: str) -> tuple[str, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL", "https://earthquake.usgs.gov/fdsnws/event/1"))
    url = f"{base_url.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=60, headers={"User-Agent": _USER_AGENT},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        text = resp.text.strip()
    except Exception as exc:
        return "", {
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    return text, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": 1,
        "error": "",
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.usgs.earthquakes"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    app_path = str(getattr(BLUEPRINT, "META_APPLICATION", "/application.json"))
    ver_path = str(getattr(BLUEPRINT, "META_VERSION", "/version"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    application, app_snap = _fetch_json(app_path)
    version_text, ver_snap = _fetch_text(ver_path)

    snapshots = [app_snap, ver_snap]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"USGS live catalog generation failed: {detail}")

    app = application if isinstance(application, dict) else {}
    catalogs = app.get("catalogs", []) if isinstance(app.get("catalogs"), list) else []
    contributors = app.get("contributors", []) if isinstance(app.get("contributors"), list) else []
    producttypes = app.get("producttypes", []) if isinstance(app.get("producttypes"), list) else []
    eventtypes = app.get("eventtypes", []) if isinstance(app.get("eventtypes"), list) else []
    magnitudetypes = app.get("magnitudetypes", []) if isinstance(app.get("magnitudetypes"), list) else []
    parameters = app.get("parameters", []) if isinstance(app.get("parameters"), list) else []

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "version": version_text,
        "enums": {
            "catalogs": catalogs,
            "contributors": contributors,
            "producttypes": producttypes,
            "eventtypes": eventtypes,
            "magnitudetypes": magnitudetypes,
        },
        "parameters": parameters,
    }

    stats = {
        "family_count": len(families),
        "catalog_count": len(catalogs),
        "catalogs_count": len(catalogs),
        "contributor_count": len(contributors),
        "contributors_count": len(contributors),
        "producttype_count": len(producttypes),
        "producttypes_count": len(producttypes),
        "eventtype_count": len(eventtypes),
        "eventtypes_count": len(eventtypes),
        "magnitudetype_count": len(magnitudetypes),
        "magnitudetypes_count": len(magnitudetypes),
        "parameter_count": len(parameters),
        "parameters_count": len(parameters),
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
        "parameter_count": stats["parameter_count"],
        "catalog_count": stats["catalog_count"],
    }
