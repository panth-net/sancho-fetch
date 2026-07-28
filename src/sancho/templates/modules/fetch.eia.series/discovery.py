"""Live catalog discovery for EIA API v2.

Walks the /v2 route tree recursively. Every node returns:
  - `routes`: sub-routes (children in the tree)
  - `facets`: dimensions you can filter by
  - `frequency`: supported frequencies
  - `data`: columns you can request

We walk up to _MAX_DEPTH levels so the catalog captures the full EIA tree
(coal, electricity, natural-gas, petroleum, international, etc.) and every
leaf-level dataset.

Requires EIA_API_KEY.
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
    spec = importlib.util.spec_from_file_location("sancho_eia_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-eia-discovery/1.0"
_MAX_DEPTH = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key() -> str:
    return os.getenv("EIA_API_KEY", "").strip()


def _fetch(route_path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/{route_path}" if route_path else f"{base_url.rstrip('/')}/"
    last_status = 0
    try:
        resp = requests.get(
            url, params={"api_key": _key()}, timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": f"route.{route_path}" if route_path else "route.root",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    return data, {
        "id": f"route.{route_path}" if route_path else "route.root",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _walk_route(
    route_path: str, depth: int, snapshots: list[dict[str, Any]], all_routes: list[dict[str, Any]],
) -> None:
    """Recursive route walker. Appends simplified node metadata to all_routes."""
    if depth > _MAX_DEPTH:
        return
    data, snap = _fetch(route_path)
    snapshots.append(snap)
    if snap.get("status") != "ok" or not isinstance(data, dict):
        return
    resp = data.get("response", {})
    if not isinstance(resp, dict):
        return
    child_routes = resp.get("routes", []) or []
    facets = resp.get("facets", []) or []
    frequency = resp.get("frequency", []) or []
    data_cols = resp.get("data", {}) or {}

    node = {
        "path": route_path,
        "id": resp.get("id"),
        "name": resp.get("name"),
        "description": resp.get("description"),
        "frequency_count": len(frequency) if isinstance(frequency, list) else 0,
        "facet_count": len(facets) if isinstance(facets, list) else 0,
        "data_column_count": len(data_cols) if isinstance(data_cols, dict) else 0,
        "child_count": len(child_routes) if isinstance(child_routes, list) else 0,
        "facets": [
            {"id": f.get("id"), "description": f.get("description")}
            for f in facets if isinstance(f, dict)
        ],
        "frequency": frequency if isinstance(frequency, list) else [],
        "data_columns": list(data_cols.keys()) if isinstance(data_cols, dict) else [],
    }
    all_routes.append(node)

    if not isinstance(child_routes, list):
        return
    for child in child_routes:
        if not isinstance(child, dict):
            continue
        child_id = child.get("id")
        if not child_id:
            continue
        next_path = f"{route_path}/{child_id}" if route_path else child_id
        _walk_route(next_path, depth + 1, snapshots, all_routes)


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.eia.series"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _key():
        raise RuntimeError(f"{provider_id} requires EIA_API_KEY env var.")

    snapshots: list[dict[str, Any]] = []
    all_routes: list[dict[str, Any]] = []
    _walk_route("", 0, snapshots, all_routes)

    ok_count = sum(1 for s in snapshots if s.get("status") == "ok")
    if ok_count == 0:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots[:5])
        raise RuntimeError(f"EIA catalog generation failed: {detail}")

    leaf_routes = [r for r in all_routes if r.get("child_count", 0) == 0]
    total_data_columns = sum(r.get("data_column_count", 0) for r in all_routes)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "routes": all_routes,
    }
    stats = {
        "family_count": len(families),
        "route_count": len(all_routes),
        "routes_count": len(all_routes),
        "leaf_route_count": len(leaf_routes),
        "leaf_routes_count": len(leaf_routes),
        "total_data_column_count": total_data_columns,
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
        "route_count": stats["route_count"],
        "leaf_route_count": stats["leaf_route_count"],
        "total_data_column_count": stats["total_data_column_count"],
    }
