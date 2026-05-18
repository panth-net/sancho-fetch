"""Live catalog discovery for Microsoft Planetary Computer STAC.

Fetches https://planetarycomputer.microsoft.com/api/stac/v1/collections which
returns every STAC collection (135 as of 2026-04) with its metadata,
temporal/spatial extents, and asset definitions. No auth required.
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
    spec = importlib.util.spec_from_file_location("sancho_pc_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-planetary-computer-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_collections() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    path = str(getattr(BLUEPRINT, "META_COLLECTIONS", "/collections"))
    url = f"{base_url.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=90,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
        collections = data.get("collections", []) if isinstance(data, dict) else []
        collections = [c for c in collections if isinstance(c, dict)]
    except Exception as exc:
        return [], {
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    return collections, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(collections),
        "error": "",
        "fetched_at": _now_iso(),
    }


def _simplify_collection(col: dict[str, Any]) -> dict[str, Any]:
    summaries = col.get("summaries", {})
    assets = col.get("item_assets") or col.get("assets") or {}
    return {
        "id": col.get("id"),
        "title": col.get("title"),
        "description": col.get("description"),
        "license": col.get("license"),
        "keywords": col.get("keywords", []),
        "providers": [p.get("name") for p in col.get("providers", []) if isinstance(p, dict)],
        "extent": col.get("extent"),
        "asset_keys": sorted(assets.keys()) if isinstance(assets, dict) else [],
        "summary_keys": sorted(summaries.keys()) if isinstance(summaries, dict) else [],
        "stac_version": col.get("stac_version"),
        "stac_extensions": col.get("stac_extensions", []),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.planetary_computer"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    collections, snap = _fetch_collections()
    snapshots = [snap]
    if snap.get("status") != "ok":
        raise RuntimeError(f"Planetary Computer STAC fetch failed: {snap.get('error')}")

    simplified = [_simplify_collection(c) for c in collections]

    keywords: set[str] = set()
    providers: set[str] = set()
    for c in simplified:
        for k in c.get("keywords", []):
            if isinstance(k, str):
                keywords.add(k)
        for p in c.get("providers", []):
            if isinstance(p, str):
                providers.add(p)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "collections": simplified,
    }
    stats = {
        "family_count": len(families),
        "collection_count": len(simplified),
        "collections_count": len(simplified),
        "keyword_count": len(keywords),
        "keywords_count": len(keywords),
        "provider_count": len(providers),
        "providers_count": len(providers),
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
        "collection_count": stats["collection_count"],
    }
