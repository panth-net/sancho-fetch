"""Shared catalog-discovery helper for Socrata civic data portals.

Every Socrata domain (data.cityofchicago.org, data.lacity.org, data.seattle.gov,
data.sfgov.org, data.cityofnewyork.us, ...) exposes the same federated catalog
endpoint at https://api.us.socrata.com/api/catalog/v1?domains={DOMAIN}. Rather
than copy-paste 300 lines of discovery.py into each per-city module, this
helper does the walk once and writes catalog.json + catalog.meta.json.

Each module's discovery.py just imports `discover_socrata` and passes its own
(provider_id, domain) pair.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


FEDERATED_URL = "https://api.us.socrata.com/api/catalog/v1"
_USER_AGENT = "sancho-socrata-discovery/1.0"
_PAGE_LIMIT = 1000
_MAX_PAGES = 50  # safety cap; 50,000 assets covers every city we target


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _socrata_auth_header() -> dict[str, str]:
    kid = os.getenv("SODA_API_KEY_ID", "").strip()
    ks = os.getenv("SODA_API_KEY_SECRET", "").strip()
    if not (kid and ks):
        return {}
    token = base64.b64encode(f"{kid}:{ks}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _fetch_page(
    *, domain: str, offset: int,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """One page of the Socrata catalog for *domain*.

    Uses the federated Socrata catalog endpoint with an explicit
    ``domains=`` filter. An earlier attempt to call each domain's own
    /api/catalog/v1 returned a global federation (ignoring implicit
    domain filtering) rather than that city's records, so we always use
    the federated endpoint with the explicit filter.
    """
    url = FEDERATED_URL
    params = {"domains": domain, "limit": _PAGE_LIMIT, "offset": offset}
    headers = {"User-Agent": _USER_AGENT, **_socrata_auth_header()}
    last_status = 0
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        last_status = resp.status_code
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("Discovery response was not an object")
        results = [r for r in payload.get("results", []) if isinstance(r, dict)]
        total_obj = payload.get("resultSetSize")
        total = int(total_obj) if isinstance(total_obj, int) else len(results)
        snap = {
            "id": f"catalog.page.{offset // _PAGE_LIMIT + 1}",
            "url": f"{url}?domains={domain}&offset={offset}",
            "status": "ok",
            "http_status": last_status,
            "count": len(results),
            "error": "",
            "fetched_at": _now_iso(),
        }
        return results, total, snap
    except Exception as exc:
        snap = {
            "id": f"catalog.page.{offset // _PAGE_LIMIT + 1}",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
        return [], 0, snap


def _build_columns(resource: dict[str, Any]) -> list[dict[str, Any]]:
    names = resource.get("columns_name") or []
    fields = resource.get("columns_field_name") or []
    datatypes = resource.get("columns_datatype") or []
    descs = resource.get("columns_description") or []
    cap = max(
        len(x) for x in (names, fields, datatypes, descs) if isinstance(x, list)
    ) if any(isinstance(x, list) for x in (names, fields, datatypes, descs)) else 0
    out: list[dict[str, Any]] = []
    for i in range(cap):
        out.append({
            "position": i,
            "name": names[i] if isinstance(names, list) and i < len(names) else "",
            "field_name": fields[i] if isinstance(fields, list) and i < len(fields) else "",
            "datatype": datatypes[i] if isinstance(datatypes, list) and i < len(datatypes) else "",
            "description": descs[i] if isinstance(descs, list) and i < len(descs) else "",
        })
    return out


def _build_asset(item: dict[str, Any]) -> dict[str, Any]:
    resource = item.get("resource") if isinstance(item.get("resource"), dict) else {}
    classification = item.get("classification") if isinstance(item.get("classification"), dict) else {}
    asset_type = str(resource.get("type", ""))
    return {
        "id": str(resource.get("id", "")),
        "name": str(resource.get("name", "")),
        "description": str(resource.get("description", "")),
        "asset_type": asset_type,
        "is_dataset": asset_type == "dataset",
        "is_live_dataset": asset_type == "dataset" and bool(resource.get("data_updated_at")),
        "attribution": str(resource.get("attribution", "")),
        "data_updated_at": resource.get("data_updated_at"),
        "updated_at": resource.get("updatedAt"),
        "download_count": resource.get("download_count"),
        "page_views": resource.get("page_views"),
        "domain_category": str(classification.get("domain_category", "")),
        "categories": [str(c) for c in (classification.get("categories") or []) if isinstance(c, str)],
        "domain_tags": [str(t) for t in (classification.get("domain_tags") or []) if isinstance(t, str)],
        "columns": _build_columns(resource),
        "permalink": str(item.get("permalink") or ""),
        "link": str(item.get("link") or ""),
    }


def _default_families(domain: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "socrata.resource",
            "base_aliases": ["v1"],
            "base_url": f"https://{domain}",
            "path_templates": ["/resource/{datasetId}.json", "/resource/{datasetId}.csv"],
            "methods": ["GET"],
            "query_params": {
                "$select": {"type": "string", "description": "Projection of columns"},
                "$where": {"type": "string", "description": "SoQL filter expression"},
                "$order": {"type": "string", "description": "Sort expression"},
                "$group": {"type": "string", "description": "Group-by expression"},
                "$having": {"type": "string", "description": "Filter on grouped rows"},
                "$limit": {"type": "int", "description": "Results per page (max 50000)"},
                "$offset": {"type": "int", "description": "Pagination offset"},
                "$q": {"type": "string", "description": "Full-text search"},
                "$$app_token": {"type": "string", "description": "Application token (rate-limit)"},
            },
            "response_mode": "json",
            "envelope_key": "",
            "description": f"SODA v2.1 query surface for any dataset on {domain}.",
            "source_refs": [f"https://{domain}/", "https://dev.socrata.com/docs/"],
        },
    ]


def discover_socrata(
    *, module_dir: Path, provider_id: str, domain: str,
    offline: bool = False, schema_version: str = "1.0",
) -> dict[str, Any]:
    """Walk the Socrata federated catalog for *domain* and persist catalog files.

    Returns the standard dict summary consumed by provider_discovery.run_module_discovery.
    """
    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    all_results: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    total = 0
    offset = 0
    for _ in range(_MAX_PAGES):
        page, total, snap = _fetch_page(domain=domain, offset=offset)
        snapshots.append(snap)
        if snap.get("status") != "ok":
            break
        if not page:
            break
        all_results.extend(page)
        offset += _PAGE_LIMIT
        if offset >= total:
            break

    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"{provider_id} live catalog generation failed: {detail}")

    assets = [_build_asset(item) for item in all_results]
    datasets = [a for a in assets if a["is_dataset"]]
    live_datasets = [a for a in datasets if a["is_live_dataset"]]
    all_tags: set[str] = set()
    for a in assets:
        for t in a.get("domain_tags", []):
            all_tags.add(t)

    families = _default_families(domain)
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "domain": domain,
        "families": families,
        "assets": assets,
        "datasets": datasets,
    }
    stats = {
        "family_count": len(families),
        "asset_count": len(assets),
        "assets_count": len(assets),
        "dataset_count": len(datasets),
        "datasets_count": len(datasets),
        "live_dataset_count": len(live_datasets),
        "live_datasets_count": len(live_datasets),
        "column_count": sum(len(a.get("columns", [])) for a in assets),
        "columns_count": sum(len(a.get("columns", [])) for a in assets),
        "tag_count": len(all_tags),
        "tags_count": len(all_tags),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [f"https://dev.socrata.com/foundry/{domain}"],
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
        "catalog": str(module_dir / "catalog.json"),
        "catalog_meta": str(module_dir / "catalog.meta.json"),
        "family_count": stats["family_count"],
        "asset_count": stats["asset_count"],
        "dataset_count": stats["dataset_count"],
    }
