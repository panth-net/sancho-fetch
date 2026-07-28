"""Live catalog discovery for openFDA.

openFDA exposes a single canonical manifest at `/download.json` that enumerates
every category (food, drug, device, animalandveterinary, transparency, tobacco,
other) and every endpoint underneath -- with bulk-download file URLs, row counts
and export dates. That manifest IS the catalog.
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
    spec = importlib.util.spec_from_file_location("sancho_openfda_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-openfda-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=60, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
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
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": 1,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _flatten_endpoints(results: Any) -> list[dict[str, Any]]:
    """Flatten /download.json `results` (category -> endpoint -> details) into rows."""
    out: list[dict[str, Any]] = []
    if not isinstance(results, dict):
        return out
    for category, endpoints in results.items():
        if not isinstance(endpoints, dict):
            continue
        for endpoint, details in endpoints.items():
            if not isinstance(details, dict):
                continue
            row = {
                "category": category,
                "endpoint": endpoint,
                "path_template": f"/{category}/{endpoint}.json",
                "export_date": details.get("export_date"),
                "total_records": details.get("total_records"),
                "partitions": details.get("partitions", []),
                "partition_count": (
                    len(details.get("partitions"))
                    if isinstance(details.get("partitions"), list) else 0
                ),
            }
            out.append(row)
    return out


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.fda.drug_events"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    manifest_path = str(getattr(BLUEPRINT, "DOWNLOAD_MANIFEST", "/download.json"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    manifest, snap = _fetch_json(manifest_path)
    snapshots = [snap]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"openFDA catalog generation failed: {detail}")

    manifest = manifest if isinstance(manifest, dict) else {}
    meta_section = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    results = manifest.get("results") if isinstance(manifest.get("results"), dict) else {}
    endpoints = _flatten_endpoints(results)

    categories = sorted({e["category"] for e in endpoints})
    total_records = sum(int(e.get("total_records") or 0) for e in endpoints)
    total_partitions = sum(int(e.get("partition_count") or 0) for e in endpoints)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "meta": meta_section,
        "categories": categories,
        "endpoints": endpoints,
    }
    stats = {
        "family_count": len(families),
        "category_count": len(categories),
        "categories_count": len(categories),
        "endpoint_count": len(endpoints),
        "endpoints_count": len(endpoints),
        "total_records": total_records,
        "total_partition_count": total_partitions,
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
        "category_count": stats["category_count"],
        "endpoint_count": stats["endpoint_count"],
    }
