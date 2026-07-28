"""Live catalog discovery for DOJ Press/Blog/Speech API.

Fetches each of the 3 content types with pagesize=1 to capture:
  - metadata.resultset.count (total record count per type)
  - sample row schema
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
    spec = importlib.util.spec_from_file_location("sancho_doj_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-doj-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, params={"pagesize": 1}, timeout=60,
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
        m = data.get("metadata", {})
        if isinstance(m, dict):
            rs = m.get("resultset", {})
            if isinstance(rs, dict):
                total_obj = rs.get("count")
                total = int(total_obj) if isinstance(total_obj, (int, str)) and str(total_obj).isdigit() else 0
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": total,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _sample_schema(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return {}
    sample = results[0]
    if not isinstance(sample, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in sample.items():
        if isinstance(v, bool):
            out[k] = "bool"
        elif isinstance(v, int):
            out[k] = "int"
        elif isinstance(v, float):
            out[k] = "float"
        elif isinstance(v, str):
            out[k] = "string"
        elif isinstance(v, list):
            out[k] = "list"
        elif isinstance(v, dict):
            out[k] = "dict"
        else:
            out[k] = "nullable"
    return out


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.doj.press_releases"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    snapshots: list[dict[str, Any]] = []
    content_types: dict[str, Any] = {}

    for path in ("/press_releases.json", "/blog_entries.json", "/speeches.json"):
        data, snap = _fetch(path)
        snapshots.append(snap)
        if snap.get("status") != "ok":
            continue
        content_types[path.strip("/").split(".")[0]] = {
            "path": path,
            "total_count": snap.get("count", 0),
            "field_schema": _sample_schema(data),
        }

    if not content_types:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots)
        raise RuntimeError(f"DOJ catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "content_types": content_types,
    }
    total_records = sum(ct.get("total_count", 0) for ct in content_types.values())
    total_fields = sum(len(ct.get("field_schema", {})) for ct in content_types.values())
    stats = {
        "family_count": len(families),
        "content_type_count": len(content_types),
        "content_types_count": len(content_types),
        "total_record_count": total_records,
        "total_field_count": total_fields,
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
        "content_type_count": stats["content_type_count"],
        "total_record_count": stats["total_record_count"],
    }
