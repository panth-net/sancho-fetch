"""Live catalog discovery for College Scorecard.

Fetches a sample school to extract the deeply-nested field tree and the
total institution count from the pagination meta. Requires DATA_GOV_API_KEY.
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
    spec = importlib.util.spec_from_file_location("sancho_scorecard_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-scorecard-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_sample() -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/schools"
    last_status = 0
    try:
        resp = requests.get(
            url,
            params={"api_key": os.getenv("DATA_GOV_API_KEY", "").strip(), "per_page": 1},
            timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": "schools.sample",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    total = 0
    if isinstance(data, dict):
        total = int(data.get("metadata", {}).get("total", 0))
    return data, {
        "id": "schools.sample",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _flatten_keys(obj: Any, prefix: str = "") -> list[str]:
    """Return dotted field paths for every leaf in a nested dict."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.extend(_flatten_keys(v, path))
            else:
                out.append(path)
    return out


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.college_scorecard.schools"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not os.getenv("DATA_GOV_API_KEY"):
        raise RuntimeError(f"{provider_id} requires DATA_GOV_API_KEY env var.")

    data, snap = _fetch_sample()
    snapshots = [snap]
    if snap.get("status") != "ok":
        raise RuntimeError(f"College Scorecard fetch failed: {snap.get('error')}")

    results = data.get("results", []) if isinstance(data, dict) else []
    sample = results[0] if results and isinstance(results[0], dict) else {}
    field_paths = _flatten_keys(sample)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "sample_school": sample,
        "field_paths": field_paths,
        "total_schools": snap.get("count", 0),
    }
    stats = {
        "family_count": len(families),
        "total_schools": snap.get("count", 0),
        "field_path_count": len(field_paths),
        "field_paths_count": len(field_paths),
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
        "total_schools": stats["total_schools"],
        "field_path_count": stats["field_path_count"],
    }
