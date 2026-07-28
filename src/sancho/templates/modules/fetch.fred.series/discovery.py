"""Live catalog discovery for FRED.

Fetches:
  GET /fred/releases?api_key=...         -> 300+ releases
  GET /fred/sources?api_key=...          ->  ~120 source organisations
  GET /fred/tags?api_key=... (paginated) -> 6,000+ tags
  GET /fred/category/children?category_id=0 -> root-level category tree

Note: /fred/tags has ~6,000 entries -- we paginate at 1000/page.
Requires FRED_API_KEY env var.
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
    spec = importlib.util.spec_from_file_location("sancho_fred_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-fred-discovery/1.0"
_PAGE = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_key() -> str:
    return os.getenv("FRED_API_KEY", "").strip()


def _fetch_json(path: str, *, params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL", "https://api.stlouisfed.org/fred"))
    url = f"{base_url.rstrip('/')}{path}"
    merged = {"api_key": _api_key(), "file_type": "json", **params}
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
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": _count(data),
        "error": "",
        "fetched_at": _now_iso(),
    }


def _count(data: Any) -> int:
    if isinstance(data, dict):
        return int(data.get("count", 0)) if "count" in data else sum(
            len(v) for v in data.values() if isinstance(v, list)
        )
    return 0


def _fetch_paginated(path: str, *, envelope_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Walk all pages of a FRED endpoint that returns {count, limit, offset, <envelope_key>: [...]}."""
    offset = 0
    all_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    while True:
        data, snap = _fetch_json(path, params={"limit": _PAGE, "offset": offset})
        snap["id"] = f"{path}.offset.{offset}"
        snapshots.append(snap)
        if snap.get("status") != "ok" or not isinstance(data, dict):
            break
        rows = data.get(envelope_key, [])
        if not isinstance(rows, list) or not rows:
            break
        all_rows.extend(r for r in rows if isinstance(r, dict))
        total = int(data.get("count", len(all_rows)))
        offset += _PAGE
        if offset >= total or len(rows) < _PAGE:
            break
    return all_rows, snapshots


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.fred.series"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _api_key():
        raise RuntimeError(f"{provider_id} requires FRED_API_KEY to generate catalog.")

    releases, release_snaps = _fetch_paginated(
        str(getattr(BLUEPRINT, "META_RELEASES", "/releases")), envelope_key="releases",
    )
    sources, source_snaps = _fetch_paginated(
        str(getattr(BLUEPRINT, "META_SOURCES", "/sources")), envelope_key="sources",
    )
    tags, tag_snaps = _fetch_paginated(
        str(getattr(BLUEPRINT, "META_TAGS", "/tags")), envelope_key="tags",
    )
    categories_raw, cat_snap = _fetch_json(
        str(getattr(BLUEPRINT, "META_CATEGORY_CHILDREN", "/category/children")),
        params={"category_id": 0},
    )

    snapshots = release_snaps + source_snaps + tag_snaps + [cat_snap]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"FRED catalog generation failed: {detail}")

    categories_root = (
        categories_raw.get("categories", []) if isinstance(categories_raw, dict) else []
    )

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "releases": releases,
        "sources": sources,
        "tags": tags,
        "categories_root": categories_root,
    }
    stats = {
        "family_count": len(families),
        "release_count": len(releases),
        "releases_count": len(releases),
        "source_count": len(sources),
        "sources_count": len(sources),
        "tag_count": len(tags),
        "tags_count": len(tags),
        "category_root_count": len(categories_root),
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
        "release_count": stats["release_count"],
        "source_count": stats["source_count"],
        "tag_count": stats["tag_count"],
    }
