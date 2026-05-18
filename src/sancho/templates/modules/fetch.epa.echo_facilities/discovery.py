"""Live catalog discovery for EPA ECHO (Enforcement & Compliance History Online).

For each ECHO sub-service (air, cwa, rcra, sdw, case, eff, dfr, echo) we fetch
its `*_rest_services.metadata` endpoint which returns the full ResultColumns
list of every queryable field. We persist per-service column schemas into
catalog.json.services[svc] so callers can discover every possible query
parameter without round-tripping.
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
    spec = importlib.util.spec_from_file_location("sancho_echo_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-epa-echo-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_metadata(service_id: str, path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, params={"output": "JSON"}, timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": f"service.{service_id}",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    results = data.get("Results") if isinstance(data, dict) else None
    columns = results.get("ResultColumns", []) if isinstance(results, dict) else []
    return data, {
        "id": f"service.{service_id}",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(columns) if isinstance(columns, list) else 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _simplify_column(col: dict[str, Any]) -> dict[str, Any]:
    return {
        "position": col.get("ColumnID") or col.get("Position"),
        "name": col.get("ColumnName"),
        "label": col.get("ObjectName") or col.get("Label"),
        "description": col.get("Description"),
        "type": col.get("DataType"),
        "length": col.get("DataLength"),
        "queryable": col.get("QueryField") or col.get("IsQueryField"),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.epa.echo_facilities"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    services = list(getattr(BLUEPRINT, "SERVICES", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    services_out: dict[str, Any] = {}
    snapshots: list[dict[str, Any]] = []
    for svc_id, path, human in services:
        data, snap = _fetch_metadata(svc_id, path)
        snapshots.append(snap)
        if snap.get("status") != "ok":
            # Not all services may be live at any given moment; record and skip.
            continue
        results = data.get("Results", {}) if isinstance(data, dict) else {}
        columns = results.get("ResultColumns", []) or []
        simplified = [_simplify_column(c) for c in columns if isinstance(c, dict)]
        services_out[svc_id] = {
            "service_id": svc_id,
            "human_name": human,
            "metadata_path": path,
            "column_count": len(simplified),
            "columns": simplified,
        }

    # Treat zero-OK as fatal, partial-OK as acceptable (some services rotate down).
    ok_services = [s for s in snapshots if s.get("status") == "ok"]
    if not ok_services:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots)
        raise RuntimeError(f"EPA ECHO catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    total_columns = sum(svc["column_count"] for svc in services_out.values())
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "services": services_out,
    }
    stats = {
        "family_count": len(families),
        "service_count": len(services_out),
        "services_count": len(services_out),
        "column_count": total_columns,
        "columns_count": total_columns,
    }
    for svc_id, svc in services_out.items():
        stats[f"service_{svc_id}_column_count"] = svc["column_count"]

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
        "service_count": stats["service_count"],
        "column_count": stats["column_count"],
    }
