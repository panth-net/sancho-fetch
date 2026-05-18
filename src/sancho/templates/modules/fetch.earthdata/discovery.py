"""Live catalog discovery for NASA CMR (Common Metadata Repository).

NASA publishes ~54,000 earth-science collections across 60 providers. We crawl:
  GET /ingest/providers                          (all 60 providers)
  GET /search/collections.json?page_size=2000    (first 2,000 collections as sample)

The full 54k collection list is too big to inline (~200 MB). The catalog's
`families` entry documents `/search/collections.json` pagination (page_num,
page_size, sort_key, bounding_box, temporal, provider) so callers can page
through the rest themselves when they need to.
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
    spec = importlib.util.spec_from_file_location("sancho_earthdata_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-earthdata-discovery/1.0"
_PAGE_SIZE = 2000
_MAX_SAMPLE_PAGES = 1  # 2,000 collections inlined is plenty for discovery purposes


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(url: str, *, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    last_status = 0
    total_hits = None
    try:
        resp = requests.get(
            url, params=params, timeout=120,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        total_hits = resp.headers.get("CMR-Hits")
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": url,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    return data, {
        "id": url,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": int(total_hits) if total_hits and total_hits.isdigit() else 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _simplify_collection(entry: dict[str, Any]) -> dict[str, Any]:
    """Trim CMR collection entries to the useful subset.

    Full entries are ~4 KB each; x54k = ~200 MB. Keeping only the queryable /
    identifying fields brings each entry to ~400-600 bytes.
    """
    organisations = entry.get("organizations", [])
    summary = entry.get("summary", "") or ""
    if len(summary) > 500:
        summary = summary[:497] + "..."
    return {
        "id": entry.get("id"),
        "concept_id": entry.get("id"),
        "short_name": entry.get("short_name"),
        "version_id": entry.get("version_id"),
        "dataset_id": entry.get("dataset_id"),
        "title": entry.get("title"),
        "summary": summary,
        "data_center": entry.get("data_center"),
        "organizations": organisations,
        "time_start": entry.get("time_start"),
        "time_end": entry.get("time_end"),
        "platforms": entry.get("platforms", []),
        "original_format": entry.get("original_format"),
        "updated": entry.get("updated"),
        "cloud_hosted": entry.get("cloud_hosted"),
        "online_access_flag": entry.get("online_access_flag"),
        "has_variables": entry.get("has_variables"),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.earthdata"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    providers_path = str(getattr(BLUEPRINT, "META_PROVIDERS", "/ingest/providers"))
    collections_path = str(getattr(BLUEPRINT, "META_COLLECTIONS", "/search/collections.json"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    providers_raw, providers_snap = _fetch_json(f"{base_url.rstrip('/')}{providers_path}")
    snapshots = [providers_snap]
    if providers_snap.get("status") != "ok":
        raise RuntimeError(f"NASA CMR providers fetch failed: {providers_snap.get('error')}")

    providers = providers_raw if isinstance(providers_raw, list) else []

    # Sample a page of collections (2000) plus record the total CMR-Hits count.
    sample_collections: list[dict[str, Any]] = []
    collections_total = 0
    for page_num in range(1, _MAX_SAMPLE_PAGES + 1):
        url = f"{base_url.rstrip('/')}{collections_path}"
        params = {"page_size": _PAGE_SIZE, "page_num": page_num}
        data, snap = _fetch_json(url, params=params)
        snap["id"] = f"collections.page.{page_num}"
        snapshots.append(snap)
        if snap.get("status") != "ok" or not isinstance(data, dict):
            break
        collections_total = max(collections_total, snap.get("count", 0))
        entries = data.get("feed", {}).get("entry", [])
        if not isinstance(entries, list) or not entries:
            break
        sample_collections.extend(_simplify_collection(e) for e in entries if isinstance(e, dict))

    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"NASA CMR catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "providers": providers,
        "collections_sample": sample_collections,
        "collections_total_in_cmr": collections_total,
    }
    stats = {
        "family_count": len(families),
        "provider_count": len(providers),
        "providers_count": len(providers),
        "collection_sample_count": len(sample_collections),
        "collections_sample_count": len(sample_collections),
        "collections_total_in_cmr": collections_total,
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
        "provider_count": stats["provider_count"],
        "collection_sample_count": stats["collection_sample_count"],
        "collections_total_in_cmr": stats["collections_total_in_cmr"],
    }
