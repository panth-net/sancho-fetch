"""Live catalog discovery for NOAA Climate Data Online.

Fetches the four small metadata endpoints in full:
  GET /datasets            (11)
  GET /datacategories      (42)
  GET /datatypes           (1,566, paginated at 1000)
  GET /locationcategories  (12)

Skips /locations and /stations -- 154,000+ stations would balloon catalog.json.
The family spec in catalog_blueprint.py documents how to page those yourself.

Requires NOAA_API_TOKEN env var (free from https://www.ncdc.noaa.gov/cdo-web/token).
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_noaa_cdo_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-noaa-cdo-discovery/1.0"
_PAGE = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token() -> str:
    return os.getenv("NOAA_API_TOKEN", "").strip()


def _fetch_paginated(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    offset = 1  # NOAA uses 1-based offset
    rows: list[dict[str, Any]] = []
    snaps: list[dict[str, Any]] = []
    while True:
        last_status = 0
        resp = None
        last_exc: Exception | None = None
        # NOAA's CDO endpoint flakes intermittently with 503/504 -- retry with
        # exponential backoff before giving up.
        for attempt in range(5):
            try:
                resp = requests.get(
                    url, params={"limit": _PAGE, "offset": offset}, timeout=90,
                    headers={"token": _token(), "User-Agent": _USER_AGENT, "Accept": "application/json"},
                )
                last_status = resp.status_code
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        else:
            resp = None
        try:
            if resp is None:
                raise last_exc or RuntimeError("exhausted retries")
            resp.raise_for_status()
            payload = resp.json()
            page = payload.get("results", []) if isinstance(payload, dict) else []
            meta = payload.get("metadata", {}).get("resultset", {}) if isinstance(payload, dict) else {}
            total = int(meta.get("count", 0))
            page_rows = [r for r in page if isinstance(r, dict)]
            snaps.append({
                "id": f"{path}.offset.{offset}",
                "url": f"{url}?offset={offset}",
                "status": "ok",
                "http_status": last_status,
                "count": len(page_rows),
                "error": "",
                "fetched_at": _now_iso(),
            })
            if not page_rows:
                break
            rows.extend(page_rows)
            offset += _PAGE
            if offset > total or len(page_rows) < _PAGE:
                break
        except Exception as exc:
            snaps.append({
                "id": f"{path}.offset.{offset}",
                "url": f"{url}?offset={offset}",
                "status": "error",
                "http_status": last_status,
                "count": 0,
                "error": str(exc),
                "fetched_at": _now_iso(),
            })
            break
    return rows, snaps


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.noaa.cdo"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _token():
        raise RuntimeError(f"{provider_id} requires NOAA_API_TOKEN env var.")

    datasets, ds_snaps = _fetch_paginated("/datasets")
    datacats, dc_snaps = _fetch_paginated("/datacategories")
    datatypes, dt_snaps = _fetch_paginated("/datatypes")
    loccats, lc_snaps = _fetch_paginated("/locationcategories")

    snapshots = ds_snaps + dc_snaps + dt_snaps + lc_snaps
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"NOAA CDO catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "datasets": datasets,
        "data_categories": datacats,
        "data_types": datatypes,
        "location_categories": loccats,
    }
    stats = {
        "family_count": len(families),
        "dataset_count": len(datasets),
        "datasets_count": len(datasets),
        "data_category_count": len(datacats),
        "data_categories_count": len(datacats),
        "data_type_count": len(datatypes),
        "data_types_count": len(datatypes),
        "location_category_count": len(loccats),
        "location_categories_count": len(loccats),
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
        "data_type_count": stats["data_type_count"],
    }
