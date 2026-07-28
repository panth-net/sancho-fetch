"""Live catalog discovery for IATI (International Aid Transparency Initiative).

Walks the 71 IATI Standard codelists at codelists.codeforiati.org/api/json/en/.
Each codelist is a reference table (Sector, Country, AidType, Currency, etc.).
We inline all of them into catalog.json.codelists so callers can resolve any
IATI code without round-tripping.
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
    spec = importlib.util.spec_from_file_location("sancho_iati_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-iati-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_codelist(name: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}/{name}.json"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=60,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": f"codelist.{name}",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    data_list = data.get("data", []) if isinstance(data, dict) else []
    return data, {
        "id": f"codelist.{name}",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(data_list) if isinstance(data_list, list) else 0,
        "error": "",
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.iati"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    codelist_names = list(getattr(BLUEPRINT, "CODELIST_NAMES", []))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    codelists: dict[str, Any] = {}
    snapshots: list[dict[str, Any]] = []
    total_entries = 0
    for name in codelist_names:
        data, snap = _fetch_codelist(name)
        snapshots.append(snap)
        if snap.get("status") != "ok" or not isinstance(data, dict):
            continue
        entries = data.get("data", [])
        codelists[name] = {
            "attributes": data.get("attributes", {}),
            "metadata": data.get("metadata", {}),
            "entry_count": len(entries) if isinstance(entries, list) else 0,
            "entries": entries if isinstance(entries, list) else [],
        }
        if isinstance(entries, list):
            total_entries += len(entries)

    ok_count = sum(1 for s in snapshots if s.get("status") == "ok")
    if ok_count == 0:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots[:5])
        raise RuntimeError(f"IATI catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "codelists": codelists,
    }
    stats = {
        "family_count": len(families),
        "codelist_count": len(codelists),
        "codelists_count": len(codelists),
        "total_codelist_entries": total_entries,
        "successful_fetches": ok_count,
        "failed_fetches": len(snapshots) - ok_count,
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
        "codelist_count": stats["codelist_count"],
        "total_codelist_entries": stats["total_codelist_entries"],
    }
