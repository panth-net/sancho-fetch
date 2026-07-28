"""Live catalog discovery for USAspending.

Walks the /api/v2/references/* family that enumerates every fixed list
(toptier agencies, award types, glossary, DEF codes, CFDA totals, NAICS/PSC/TAS
filter trees). Stores them under catalog.json.references so callers can discover
valid filter values without round-tripping.
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
    spec = importlib.util.spec_from_file_location("sancho_usaspending_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-usaspending-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
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
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    count = 0
    if isinstance(data, list):
        count = len(data)
    elif isinstance(data, dict):
        for k in ("results", "codes", "children", "data"):
            if isinstance(data.get(k), list):
                count = len(data[k])
                break
        if count == 0:
            count = len(data)
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": count,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _extract(payload: Any, envelope_key: str) -> Any:
    """Extract the list from an envelope key, or return the payload itself."""
    if not isinstance(payload, dict) or not envelope_key:
        return payload
    value = payload.get(envelope_key)
    return value if value is not None else payload


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.usaspending.awards"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    meta_endpoints = list(getattr(BLUEPRINT, "META_ENDPOINTS", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    references: dict[str, Any] = {}
    snapshots: list[dict[str, Any]] = []
    for key, path, envelope_key in meta_endpoints:
        payload, snap = _fetch_json(path)
        snap["id"] = f"meta.{key}"
        snapshots.append(snap)
        if snap.get("status") != "ok":
            continue
        references[key] = _extract(payload, envelope_key)

    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        # Treat partial failures as non-fatal -- USAspending occasionally times out
        # on filter_tree/psc. Log via snapshots and continue so the catalog still
        # captures the other references.
        if len(failures) == len(meta_endpoints):
            raise RuntimeError(f"USAspending catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "references": references,
    }

    # Compute per-reference counts for meta.stats.
    stats: dict[str, int] = {
        "family_count": len(families),
        "reference_count": len(references),
        "references_count": len(references),
    }
    for key, value in references.items():
        if isinstance(value, list):
            stats[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            stats[f"{key}_keys"] = len(value)
    # Total refs with data
    stats["successful_references"] = sum(
        1 for s in snapshots if s.get("status") == "ok"
    )

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
        "reference_count": stats["reference_count"],
        "successful_references": stats["successful_references"],
    }
