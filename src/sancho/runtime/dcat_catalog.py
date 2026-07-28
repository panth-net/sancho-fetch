"""Shared catalog-discovery helper for DCAT /data.json catalogs.

Every federal data portal (and many state/city portals) exposes its catalog
at `/data.json` in the DCAT-US schema. One HTTP GET returns every dataset
with its title, description, distribution URLs, temporal range, and license.

Each module's discovery.py imports `discover_dcat` and passes its own
(provider_id, base_url) pair.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


_USER_AGENT = "sancho-dcat-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_data_json(base_url: str) -> tuple[Any, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/data.json"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=120,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": "/data.json",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    ds = data.get("dataset") if isinstance(data, dict) else None
    return data, {
        "id": "/data.json",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(ds) if isinstance(ds, list) else 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _simplify_dataset(ds: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields a caller is likely to query against.

    DCAT dataset entries are large (30+ fields); this prunes to the useful
    subset so catalog.json stays readable.
    """
    distributions = ds.get("distribution")
    if isinstance(distributions, list):
        simplified_distributions = [
            {
                "title": d.get("title"),
                "description": d.get("description"),
                "mediaType": d.get("mediaType"),
                "format": d.get("format"),
                "downloadURL": d.get("downloadURL"),
                "accessURL": d.get("accessURL"),
            }
            for d in distributions if isinstance(d, dict)
        ]
    else:
        simplified_distributions = []

    return {
        "identifier": ds.get("identifier"),
        "title": ds.get("title"),
        "description": ds.get("description"),
        "modified": ds.get("modified"),
        "issued": ds.get("issued"),
        "temporal": ds.get("temporal"),
        "accessLevel": ds.get("accessLevel"),
        "accrualPeriodicity": ds.get("accrualPeriodicity"),
        "keyword": ds.get("keyword", []),
        "theme": ds.get("theme", []),
        "publisher": ds.get("publisher", {}).get("name") if isinstance(ds.get("publisher"), dict) else None,
        "contactPoint": ds.get("contactPoint", {}).get("fn") if isinstance(ds.get("contactPoint"), dict) else None,
        "license": ds.get("license"),
        "landingPage": ds.get("landingPage"),
        "describedBy": ds.get("describedBy"),
        "distribution": simplified_distributions,
    }


def discover_dcat(
    *, module_dir: Path, provider_id: str, base_url: str,
    docs_url: str = "", offline: bool = False, schema_version: str = "1.0",
    families: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch /data.json from *base_url* and persist catalog files."""
    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    data, snap = _fetch_data_json(base_url)
    snapshots = [snap]
    if snap.get("status") != "ok":
        raise RuntimeError(f"{provider_id} /data.json fetch failed: {snap.get('error')}")

    data = data if isinstance(data, dict) else {}
    raw_datasets = data.get("dataset") if isinstance(data.get("dataset"), list) else []
    datasets = [_simplify_dataset(d) for d in raw_datasets if isinstance(d, dict)]

    keywords: set[str] = set()
    themes: set[str] = set()
    publishers: set[str] = set()
    total_distributions = 0
    for d in datasets:
        for k in d.get("keyword", []):
            if isinstance(k, str):
                keywords.add(k)
        for t in d.get("theme", []):
            if isinstance(t, str):
                themes.add(t)
        if d.get("publisher"):
            publishers.add(d["publisher"])
        total_distributions += len(d.get("distribution", []))

    effective_families = families or [
        {
            "id": "dcat.dataset",
            "base_aliases": ["v1"],
            "base_url": base_url,
            "path_templates": ["/data.json"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "dataset",
            "description": f"DCAT-US catalog for {base_url}. One HTTP GET returns every dataset.",
            "source_refs": [docs_url] if docs_url else [],
        },
    ]

    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "conformsTo": data.get("conformsTo"),
        "describedBy": data.get("describedBy"),
        "families": effective_families,
        "datasets": datasets,
    }
    stats = {
        "family_count": len(effective_families),
        "dataset_count": len(datasets),
        "datasets_count": len(datasets),
        "distribution_count": total_distributions,
        "distributions_count": total_distributions,
        "keyword_count": len(keywords),
        "keywords_count": len(keywords),
        "theme_count": len(themes),
        "themes_count": len(themes),
        "publisher_count": len(publishers),
        "publishers_count": len(publishers),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [docs_url] if docs_url else [],
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
        "distribution_count": stats["distribution_count"],
    }
