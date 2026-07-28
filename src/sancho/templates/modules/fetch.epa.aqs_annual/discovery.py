"""Live catalog discovery for EPA AQS (Air Quality System).

Walks:
  - 7 simple /list/ endpoints (states, cbsas, classes, pqaos, mas, durations, ...)
  - /list/parametersByClass for every class (AQI POLLUTANTS, HAPS, etc.)

The goal is to inline every enumeration value callers might need without
round-tripping. Requires AQS_API_KEY + AQS_EMAIL.
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
    spec = importlib.util.spec_from_file_location("sancho_aqs_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-aqs-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth() -> dict[str, str]:
    return {
        "email": os.getenv("AQS_EMAIL", "").strip(),
        "key": os.getenv("AQS_API_KEY", "").strip(),
    }


def _fetch(path: str, *, extra: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/{path}"
    params = {**_auth(), **(extra or {})}
    last_status = 0
    try:
        resp = requests.get(
            url, params=params, timeout=60,
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
    items = data.get("Data", []) if isinstance(data, dict) else []
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(items) if isinstance(items, list) else 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.epa.aqs_annual"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _auth().get("key") or not _auth().get("email"):
        raise RuntimeError(f"{provider_id} requires AQS_API_KEY + AQS_EMAIL env vars.")

    snapshots: list[dict[str, Any]] = []
    lists: dict[str, Any] = {}

    # Simple lists -- no extra params needed.
    for path in ("list/states", "list/cbsas", "list/classes", "list/pqaos", "list/mas", "list/durations"):
        data, snap = _fetch(path)
        snapshots.append(snap)
        if snap.get("status") == "ok":
            lists[path.split("/")[-1]] = data.get("Data", [])

    # Parameters by class: walk every class returned by /list/classes.
    classes = lists.get("classes", []) or []
    parameters_by_class: dict[str, list[Any]] = {}
    for cls in classes:
        pc = cls.get("code") if isinstance(cls, dict) else None
        if not pc:
            continue
        data, snap = _fetch("list/parametersByClass", extra={"pc": pc})
        snap["id"] = f"parametersByClass.{pc}"
        snapshots.append(snap)
        if snap.get("status") == "ok":
            parameters_by_class[pc] = data.get("Data", [])

    ok_count = sum(1 for s in snapshots if s.get("status") == "ok")
    if ok_count < 3:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots if s.get("status") != "ok")[:400]
        raise RuntimeError(f"EPA AQS catalog generation failed: {detail}")

    total_params = sum(len(v) for v in parameters_by_class.values() if isinstance(v, list))
    total_list_entries = sum(len(v) for v in lists.values() if isinstance(v, list))

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "lists": lists,
        "parameters_by_class": parameters_by_class,
    }
    stats = {
        "family_count": len(families),
        "list_count": len(lists),
        "lists_count": len(lists),
        "total_list_entry_count": total_list_entries,
        "parameter_class_count": len(parameters_by_class),
        "total_parameter_count": total_params,
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
        "list_count": stats["list_count"],
        "total_parameter_count": stats["total_parameter_count"],
    }
