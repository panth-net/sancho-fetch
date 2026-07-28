"""Live catalog discovery for USDA Quickstats (NASS).

Walks `get_param_values/?param={name}` for every enumerable dimension
(source, sector, group, commodity, state, ...) so callers can query any
combination without round-tripping to discover valid values.

Requires USDA_NASS_API_KEY env var.
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
    spec = importlib.util.spec_from_file_location("sancho_quickstats_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-quickstats-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key() -> str:
    return os.getenv("USDA_NASS_API_KEY", "").strip()


def _fetch_param_values(param: str) -> tuple[list[Any], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/get_param_values/"
    last_status = 0
    last_exc: Exception | None = None
    # NASS occasionally 429s -- small retry backoff.
    for attempt in range(3):
        try:
            resp = requests.get(
                url, params={"key": _key(), "param": param}, timeout=60,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            last_status = resp.status_code
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            values = data.get(param, []) if isinstance(data, dict) else []
            return values if isinstance(values, list) else [], {
                "id": f"param.{param}",
                "url": url,
                "status": "ok",
                "http_status": last_status,
                "count": len(values) if isinstance(values, list) else 0,
                "error": "",
                "fetched_at": _now_iso(),
            }
        except Exception as exc:
            last_exc = exc
            time.sleep(2 ** attempt)
    return [], {
        "id": f"param.{param}",
        "url": url,
        "status": "error",
        "http_status": last_status,
        "count": 0,
        "error": str(last_exc or "unknown"),
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.usda.quickstats"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    enumerable = list(getattr(BLUEPRINT, "ENUMERABLE_PARAMS", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _key():
        raise RuntimeError(f"{provider_id} requires USDA_NASS_API_KEY env var.")

    parameters: dict[str, Any] = {}
    snapshots: list[dict[str, Any]] = []
    for param in enumerable:
        values, snap = _fetch_param_values(param)
        snapshots.append(snap)
        if snap.get("status") != "ok":
            parameters[param] = {"value_count": 0, "values": [], "error": snap.get("error")}
            continue
        parameters[param] = {
            "value_count": len(values),
            "values": values,
        }

    ok_count = sum(1 for s in snapshots if s.get("status") == "ok")
    if ok_count == 0:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots[:5])
        raise RuntimeError(f"Quickstats catalog generation failed: {detail}")

    total_values = sum(p.get("value_count", 0) for p in parameters.values())
    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "parameters": parameters,
    }
    stats = {
        "family_count": len(families),
        "parameter_count": len(parameters),
        "parameters_count": len(parameters),
        "total_value_count": total_values,
        "total_values_count": total_values,
        "successful_params": ok_count,
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
        "parameter_count": stats["parameter_count"],
        "total_value_count": stats["total_value_count"],
    }
