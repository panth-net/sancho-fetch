"""Live catalog discovery for Congress.gov API v3.

For each of the 17+ top-level resources (bill, amendment, member, committee,
nomination, hearing, treaty, ...) we hit the root endpoint to:
  - verify the path
  - capture pagination meta (count)
  - grab a 1-item sample of the row shape

Full enumeration of bills (hundreds of thousands) is not inlined -- callers can
use the pagination params documented in families to walk them.
Requires CONGRESS_API_KEY env var.
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
    spec = importlib.util.spec_from_file_location("sancho_congress_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-congress-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key() -> str:
    return os.getenv("CONGRESS_API_KEY", "").strip()


def _fetch(path: str, *, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    merged = {"api_key": _key(), "format": "json", "limit": 1, **(params or {})}
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
    total = 0
    pagination = data.get("pagination") if isinstance(data, dict) else None
    if isinstance(pagination, dict):
        total = int(pagination.get("count", 0)) if isinstance(pagination.get("count"), int) else 0
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _extract_sample(data: Any, envelope_key: str) -> Any:
    if not isinstance(data, dict):
        return None
    # Some responses use nested dotted paths (e.g. Results.Issues).
    node = data
    for part in envelope_key.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    if isinstance(node, list) and node:
        return node[0]
    return node


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.congress.bills"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    resources = list(getattr(BLUEPRINT, "RESOURCES", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _key():
        raise RuntimeError(f"{provider_id} requires CONGRESS_API_KEY env var.")

    # Special: /congress itself is small enough to inline fully.
    congresses_data, congresses_snap = _fetch("/congress", params={"limit": 250})
    snapshots = [congresses_snap]
    congresses = []
    if congresses_snap.get("status") == "ok":
        node = _extract_sample(congresses_data, "")
        if isinstance(congresses_data, dict):
            congresses = congresses_data.get("congresses", [])
    congresses = congresses if isinstance(congresses, list) else []

    resource_meta: list[dict[str, Any]] = []
    for path, envelope, desc in resources:
        if path == "/congress":
            # Already fetched above.
            resource_meta.append({
                "path": path,
                "envelope_key": envelope,
                "description": desc,
                "total_count": len(congresses),
                "sample_row_keys": list(congresses[0].keys()) if congresses and isinstance(congresses[0], dict) else [],
            })
            continue
        data, snap = _fetch(path)
        snapshots.append(snap)
        if snap.get("status") != "ok":
            resource_meta.append({
                "path": path,
                "envelope_key": envelope,
                "description": desc,
                "total_count": None,
                "sample_row_keys": [],
                "error": snap.get("error"),
            })
            continue
        sample = _extract_sample(data, envelope)
        resource_meta.append({
            "path": path,
            "envelope_key": envelope,
            "description": desc,
            "total_count": snap.get("count"),
            "sample_row_keys": list(sample.keys()) if isinstance(sample, dict) else [],
        })

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "congresses": congresses,
        "resources": resource_meta,
    }
    total_items = sum(r.get("total_count") or 0 for r in resource_meta)
    stats = {
        "family_count": len(families),
        "resource_count": len(resource_meta),
        "resources_count": len(resource_meta),
        "congress_count": len(congresses),
        "total_items_across_resources": total_items,
        "successful_resources": sum(1 for r in resource_meta if r.get("total_count") is not None),
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
        "resource_count": stats["resource_count"],
        "congress_count": stats["congress_count"],
        "successful_resources": stats["successful_resources"],
    }
