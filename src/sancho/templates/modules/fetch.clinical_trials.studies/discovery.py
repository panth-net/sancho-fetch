"""Live catalog discovery for ClinicalTrials.gov v2.

ClinicalTrials.gov does not publish a standard OpenAPI/Swagger spec, but it
exposes a family of self-describing metadata endpoints that enumerate the
entire API surface:

  GET /api/v2/studies/metadata        (recursive tree of every Study field)
  GET /api/v2/studies/search-areas    (search-area groups with field lists)
  GET /api/v2/studies/enums           (enum types + allowed values)
  GET /api/v2/version                 (API version + data-load timestamp)
  GET /api/v2/stats/size              (size percentiles across all studies)

We materialise each into catalog.json so downstream callers can enumerate
valid query parameters without round-tripping to the provider.
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
    spec = importlib.util.spec_from_file_location(
        "sancho_clinical_trials_catalog_blueprint", path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-clinical-trials-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL", "https://clinicaltrials.gov/api/v2"))
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
    count = _node_count(data)
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": count,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _node_count(value: Any) -> int:
    """Rough cardinality for provenance. Lists count length; dicts count 1."""
    if isinstance(value, list):
        total = 0
        for item in value:
            if isinstance(item, dict) and "children" in item:
                total += 1 + _node_count(item.get("children", []))
            else:
                total += 1
        return total
    if isinstance(value, dict):
        return 1
    return 0


def _flatten_metadata(nodes: Any, *, path: str = "") -> list[dict[str, Any]]:
    """Flatten the recursive studies/metadata tree into a list of field dicts.

    Each entry gets a dotted `path` (e.g. 'protocolSection.identificationModule.nctId').
    """
    out: list[dict[str, Any]] = []
    if not isinstance(nodes, list):
        return out
    for node in nodes:
        if not isinstance(node, dict):
            continue
        name = node.get("name") or node.get("piece") or ""
        full_path = f"{path}.{name}" if path and name else (name or path)
        out.append({
            "path": full_path,
            "name": name,
            "piece": node.get("piece"),
            "title": node.get("title"),
            "type": node.get("type"),
            "sourceType": node.get("sourceType"),
            "dedLink": node.get("dedLink"),
            "rules": node.get("rules"),
            "maxChars": node.get("maxChars"),
        })
        children = node.get("children")
        if isinstance(children, list) and children:
            out.extend(_flatten_metadata(children, path=full_path))
    return out


def _write_catalog_files(
    module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any],
) -> None:
    (module_dir / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )
    (module_dir / "catalog.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.clinical_trials.studies"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    metadata_raw, meta_snap = _fetch_json(getattr(BLUEPRINT, "META_STUDIES", "/studies/metadata"))
    areas_raw, areas_snap = _fetch_json(getattr(BLUEPRINT, "META_SEARCH_AREAS", "/studies/search-areas"))
    enums_raw, enums_snap = _fetch_json(getattr(BLUEPRINT, "META_ENUMS", "/studies/enums"))
    version_raw, version_snap = _fetch_json(getattr(BLUEPRINT, "META_VERSION", "/version"))
    size_raw, size_snap = _fetch_json(getattr(BLUEPRINT, "META_SIZE", "/stats/size"))

    snapshots = [meta_snap, areas_snap, enums_snap, version_snap, size_snap]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"ClinicalTrials.gov live catalog generation failed: {detail}")

    fields_flat = _flatten_metadata(metadata_raw or [])
    enum_values_total = 0
    if isinstance(enums_raw, list):
        enum_values_total = sum(
            len(e.get("values", [])) for e in enums_raw if isinstance(e, dict)
        )

    search_area_total = 0
    if isinstance(areas_raw, list):
        search_area_total = sum(
            len(sa.get("areas", [])) for sa in areas_raw if isinstance(sa, dict)
        )

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "metadata_tree": metadata_raw,
        "fields_flat": fields_flat,
        "search_areas": areas_raw,
        "enums": enums_raw,
        "version": version_raw,
        "size_stats": size_raw,
    }

    stats = {
        "family_count": len(families),
        "field_count": len(fields_flat),
        "fields_count": len(fields_flat),
        "enum_type_count": len(enums_raw) if isinstance(enums_raw, list) else 0,
        "enum_types_count": len(enums_raw) if isinstance(enums_raw, list) else 0,
        "enum_value_count": enum_values_total,
        "enum_values_count": enum_values_total,
        "search_area_count": search_area_total,
        "search_areas_count": search_area_total,
        "total_studies": (size_raw or {}).get("totalStudies", 0) if isinstance(size_raw, dict) else 0,
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

    _write_catalog_files(module_dir, catalog, meta)
    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "catalog": str(module_dir / "catalog.json"),
        "catalog_meta": str(module_dir / "catalog.meta.json"),
        "family_count": stats["family_count"],
        "field_count": stats["field_count"],
        "enum_type_count": stats["enum_type_count"],
        "enum_value_count": stats["enum_value_count"],
    }
