"""Live catalog discovery for FDIC BankFind.

For each of the 3 top-level data families we fetch a 1-record sample to
extract the full field schema from the response envelope. Also captures the
total record count from the meta.total field.
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
    spec = importlib.util.spec_from_file_location("sancho_fdic_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-fdic-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch(path: str, *, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    merged = {"limit": 1, "format": "json", **(params or {})}
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
    if isinstance(data, dict):
        m = data.get("meta", {})
        if isinstance(m, dict):
            total_obj = m.get("total") or m.get("count")
            total = int(total_obj) if isinstance(total_obj, int) else 0
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _extract_field_schema(data: Any) -> dict[str, str]:
    """FDIC wraps each row as {data: {...}, score: n}. The inner `data` has all fields."""
    if not isinstance(data, dict):
        return {}
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        return {}
    sample = rows[0]
    inner = sample.get("data") if isinstance(sample, dict) else None
    if not isinstance(inner, dict):
        return {}
    # Build simple name -> type map (inferred from runtime values).
    out: dict[str, str] = {}
    for k, v in inner.items():
        if isinstance(v, bool):
            t = "bool"
        elif isinstance(v, int):
            t = "int"
        elif isinstance(v, float):
            t = "float"
        elif isinstance(v, str):
            t = "string"
        elif v is None:
            t = "nullable"
        else:
            t = type(v).__name__
        out[k] = t
    return out


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.fdic.institutions"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    resources = list(getattr(BLUEPRINT, "RESOURCES", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    resource_meta: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    total_fields = 0
    for path, envelope, desc in resources:
        data, snap = _fetch(path)
        snapshots.append(snap)
        if snap.get("status") != "ok":
            continue
        schema = _extract_field_schema(data)
        total_fields += len(schema)
        resource_meta.append({
            "path": path,
            "envelope_key": envelope,
            "description": desc,
            "total_count": snap.get("count"),
            "field_count": len(schema),
            "fields": schema,
        })

    if not resource_meta:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots)
        raise RuntimeError(f"FDIC BankFind catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "resources": resource_meta,
    }
    stats = {
        "family_count": len(families),
        "resource_count": len(resource_meta),
        "resources_count": len(resource_meta),
        "total_field_count": total_fields,
        "fields_count": total_fields,
        "total_records_across_resources": sum(r.get("total_count") or 0 for r in resource_meta),
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
        "total_field_count": stats["total_field_count"],
    }
