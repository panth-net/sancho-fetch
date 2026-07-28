from __future__ import annotations

import json
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_world_bank_catalog_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

BLUEPRINT = _load_blueprint()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_json(url: str, *, params: dict[str, Any] | None) -> tuple[Any, int]:
    response = requests.get(
        url,
        params=params or None,
        timeout=30,
        headers={"User-Agent": "sancho-world-bank-discovery/1.0"},
    )
    response.raise_for_status()
    return response.json(), response.status_code


def _v2_url(path: str) -> str:
    base_url = str(getattr(BLUEPRINT, "V2_BASE_URL", "https://api.worldbank.org/v2"))
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _extract_v2_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
        return payload[1]
    return []


def _extract_v2_total_pages(payload: Any) -> int:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        pages = payload[0].get("pages", 1)
        if isinstance(pages, int) and pages > 0:
            return pages
    return 1


def _fetch_v2_collection(path: str, *, params: dict[str, Any]) -> tuple[list[Any], int]:
    page = 1
    total_pages = 1
    all_rows: list[Any] = []
    last_status = 200
    while page <= total_pages:
        current_params = dict(params)
        current_params["page"] = page
        payload, status = _request_json(_v2_url(path), params=current_params)
        last_status = status
        rows = _extract_v2_rows(payload)
        all_rows.extend(rows)
        total_pages = _extract_v2_total_pages(payload)
        page += 1
        if page > 1000:
            raise RuntimeError(f"Exceeded safety page limit while fetching {path}")
    return all_rows, last_status


def _build_snapshot(source_id: str, url: str, *, status: str, count: int, http_status: int, error: str = "") -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "id": source_id,
        "url": url,
        "status": status,
        "http_status": http_status,
        "count": count,
        "fetched_at": _now_iso(),
    }
    if error:
        snapshot["error"] = error
    return snapshot


def _fetch_v2_source(source_id: str, path: str, *, params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    url = _v2_url(path)
    try:
        rows, status = _fetch_v2_collection(path, params=params)
        return rows, _build_snapshot(source_id, url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot(source_id, url, status="error", count=0, http_status=0, error=str(exc))


def _fetch_projects_index() -> tuple[list[Any], dict[str, Any]]:
    projects_base = str(getattr(BLUEPRINT, "PROJECTS_BASE_URL", "https://search.worldbank.org/api/v2"))
    url = f"{projects_base}/projects"
    params = {"format": "json", "rows": 200, "os": 0}
    try:
        payload, status = _request_json(url, params=params)
        projects_obj = payload.get("projects", {}) if isinstance(payload, dict) else {}
        rows = list(projects_obj.values()) if isinstance(projects_obj, dict) else []
        return rows, _build_snapshot("projects.index", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("projects.index", url, status="error", count=0, http_status=0, error=str(exc))


def _fetch_ddh_datasets() -> tuple[list[Any], dict[str, Any]]:
    ddh_base = str(getattr(BLUEPRINT, "DDH_BASE_URL", "https://ddh-openapi.worldbank.org"))
    url = f"{ddh_base}/datasets"
    params = {"size": 200, "page": 1}
    try:
        payload, status = _request_json(url, params=params)
        rows: list[Any] = []
        if isinstance(payload, dict):
            datasets_obj = payload.get("datasets")
            if isinstance(datasets_obj, list):
                rows = datasets_obj
            results_obj = payload.get("results")
            if isinstance(results_obj, list):
                rows = results_obj
            items_obj = payload.get("items")
            if isinstance(items_obj, list):
                rows = items_obj
        return rows, _build_snapshot("ddh.datasets", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("ddh.datasets", url, status="error", count=0, http_status=0, error=str(exc))


def _write_catalog_files(module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any]) -> None:
    catalog_path = module_dir / "catalog.json"
    meta_path = module_dir / "catalog.meta.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.world_bank"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_base = str(getattr(BLUEPRINT, "DOCS_BASE", ""))
    docs_basic = str(getattr(BLUEPRINT, "DOCS_BASIC", ""))
    docs_projects = str(getattr(BLUEPRINT, "DOCS_PROJECTS", ""))
    docs_ddh = str(getattr(BLUEPRINT, "DOCS_DDH", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    indicators, indicators_snapshot = _fetch_v2_source("v2.indicators", "/indicator", params={"format": "json", "per_page": 20000})
    sources, sources_snapshot = _fetch_v2_source("v2.sources", "/sources", params={"format": "json", "per_page": 20000})
    topics, topics_snapshot = _fetch_v2_source("v2.topics", "/topic", params={"format": "json", "per_page": 20000})
    countries, countries_snapshot = _fetch_v2_source("v2.countries", "/country", params={"format": "json", "per_page": 20000})
    income_levels, income_snapshot = _fetch_v2_source("v2.income_levels", "/incomelevel", params={"format": "json", "per_page": 500})
    lending_types, lending_snapshot = _fetch_v2_source("v2.lending_types", "/lendingtype", params={"format": "json", "per_page": 500})
    regions, regions_snapshot = _fetch_v2_source("v2.regions", "/region", params={"format": "json", "per_page": 500})
    projects, projects_snapshot = _fetch_projects_index()
    ddh_datasets, ddh_snapshot = _fetch_ddh_datasets()

    snapshots = [
        indicators_snapshot,
        sources_snapshot,
        topics_snapshot,
        countries_snapshot,
        income_snapshot,
        lending_snapshot,
        regions_snapshot,
        projects_snapshot,
        ddh_snapshot,
    ]
    failures = [item for item in snapshots if item.get("status") != "ok"]
    if failures:
        detail = "; ".join([f"{item.get('id')}: {item.get('error', 'unknown error')}" for item in failures])
        raise RuntimeError(f"World Bank live catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "indices": {
            "indicators": indicators,
            "sources": sources,
            "topics": topics,
            "countries": countries,
            "income_levels": income_levels,
            "lending_types": lending_types,
            "regions": regions,
            "projects": projects,
            "ddh_datasets": ddh_datasets,
        },
    }

    stats = {
        "family_count": len(families),
        "indicator_count": len(indicators),
        "indicators_count": len(indicators),
        "source_count": len(sources),
        "sources_count": len(sources),
        "topic_count": len(topics),
        "topics_count": len(topics),
        "country_count": len(countries),
        "countries_count": len(countries),
        "income_level_count": len(income_levels),
        "income_levels_count": len(income_levels),
        "lending_type_count": len(lending_types),
        "lending_types_count": len(lending_types),
        "region_count": len(regions),
        "regions_count": len(regions),
        "project_count": len(projects),
        "projects_count": len(projects),
        "ddh_dataset_count": len(ddh_datasets),
        "ddh_datasets_count": len(ddh_datasets),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [docs_base, docs_basic, docs_projects, docs_ddh],
        },
    }

    _write_catalog_files(module_dir, catalog, meta)
    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "catalog": str(module_dir / "catalog.json"),
        "catalog_meta": str(module_dir / "catalog.meta.json"),
        "family_count": stats["family_count"],
        "indicator_count": stats["indicator_count"],
        "source_count": stats["source_count"],
        "topic_count": stats["topic_count"],
        "status": "ok",
    }
