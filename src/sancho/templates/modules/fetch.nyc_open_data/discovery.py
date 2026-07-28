from __future__ import annotations

import base64
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_nyc_open_data_catalog_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BLUEPRINT = _load_blueprint()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Any, int]:
    response = requests.get(
        url,
        params=params or None,
        headers=headers or None,
        timeout=45,
    )
    response.raise_for_status()
    return response.json(), response.status_code


def _build_snapshot(
    source_id: str,
    url: str,
    *,
    status: str,
    count: int,
    http_status: int,
    offset: int | None = None,
    limit: int | None = None,
    total_results: int | None = None,
    error: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": source_id,
        "url": url,
        "status": status,
        "http_status": http_status,
        "count": count,
        "fetched_at": _now_iso(),
    }
    if offset is not None:
        payload["offset"] = offset
    if limit is not None:
        payload["limit"] = limit
    if total_results is not None:
        payload["total_results"] = total_results
    if error:
        payload["error"] = error
    return payload


def _discovery_url() -> str:
    base = str(getattr(BLUEPRINT, "DISCOVERY_BASE_URL", "https://api.us.socrata.com"))
    return f"{base.rstrip('/')}/api/catalog/v1"


def _fetch_catalog_page(
    *,
    offset: int,
    limit: int,
    headers: dict[str, str],
) -> tuple[list[dict[str, Any]], int, int, dict[str, Any]]:
    url = _discovery_url()
    params = {
        "domains": getattr(BLUEPRINT, "DOMAIN", "data.cityofnewyork.us"),
        "limit": limit,
        "offset": offset,
    }
    try:
        payload, status = _request_json(url, params=params, headers=headers)
        if not isinstance(payload, dict):
            raise ValueError("Discovery response was not an object")
        results_obj = payload.get("results", [])
        results = [item for item in results_obj if isinstance(item, dict)] if isinstance(results_obj, list) else []
        total_results_obj = payload.get("resultSetSize", len(results))
        total_results = int(total_results_obj) if isinstance(total_results_obj, int) else len(results)
        snapshot = _build_snapshot(
            f"catalog.page.{offset // limit + 1}",
            url,
            status="ok",
            count=len(results),
            http_status=status,
            offset=offset,
            limit=limit,
            total_results=total_results,
        )
        return results, total_results, status, snapshot
    except Exception as exc:
        snapshot = _build_snapshot(
            f"catalog.page.{offset // limit + 1}",
            url,
            status="error",
            count=0,
            http_status=0,
            offset=offset,
            limit=limit,
            total_results=0,
            error=str(exc),
        )
        return [], 0, 0, snapshot


def _build_columns(resource: dict[str, Any]) -> list[dict[str, Any]]:
    names = resource.get("columns_name", [])
    fields = resource.get("columns_field_name", [])
    datatypes = resource.get("columns_datatype", [])
    descriptions = resource.get("columns_description", [])
    formats = resource.get("columns_format", [])
    max_len = max(
        len(names) if isinstance(names, list) else 0,
        len(fields) if isinstance(fields, list) else 0,
        len(datatypes) if isinstance(datatypes, list) else 0,
        len(descriptions) if isinstance(descriptions, list) else 0,
        len(formats) if isinstance(formats, list) else 0,
    )
    values: list[dict[str, Any]] = []
    for idx in range(max_len):
        values.append(
            {
                "position": idx,
                "name": names[idx] if isinstance(names, list) and idx < len(names) else "",
                "field_name": fields[idx] if isinstance(fields, list) and idx < len(fields) else "",
                "datatype": datatypes[idx] if isinstance(datatypes, list) and idx < len(datatypes) else "",
                "description": descriptions[idx] if isinstance(descriptions, list) and idx < len(descriptions) else "",
                "format": formats[idx] if isinstance(formats, list) and idx < len(formats) else {},
            }
        )
    return values


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _build_catalog_asset(item: dict[str, Any]) -> dict[str, Any]:
    resource_obj = item.get("resource", {})
    resource = resource_obj if isinstance(resource_obj, dict) else {}
    classification_obj = item.get("classification", {})
    classification = classification_obj if isinstance(classification_obj, dict) else {}
    metadata_obj = item.get("metadata", {})
    metadata = metadata_obj if isinstance(metadata_obj, dict) else {}
    permalink_obj = item.get("permalink")
    link_obj = item.get("link")

    asset_type = str(resource.get("type", ""))
    is_dataset_asset = asset_type == "dataset"
    data_updated_at = resource.get("data_updated_at")
    is_live_dataset = is_dataset_asset and data_updated_at not in (None, "")

    entry: dict[str, Any] = {
        "id": str(resource.get("id", "")),
        "name": str(resource.get("name", "")),
        "description": str(resource.get("description", "")),
        "type": asset_type,
        "asset_type": asset_type,
        "is_dataset_asset": is_dataset_asset,
        "is_live_dataset": is_live_dataset,
        "attribution": str(resource.get("attribution", "")),
        "created_at": resource.get("createdAt"),
        "updated_at": resource.get("updatedAt"),
        "metadata_updated_at": resource.get("metadata_updated_at"),
        "data_updated_at": resource.get("data_updated_at"),
        "publication_date": resource.get("publication_date"),
        "download_count": resource.get("download_count"),
        "page_views": resource.get("page_views"),
        "domain": str((metadata.get("domain", "") if isinstance(metadata, dict) else "")),
        "domain_category": str(classification.get("domain_category", "")),
        "categories": _coerce_str_list(classification.get("categories", [])),
        "domain_tags": _coerce_str_list(classification.get("domain_tags", [])),
        "tags": _coerce_str_list(classification.get("tags", [])),
        "columns": _build_columns(resource),
        "permalink": str(permalink_obj) if isinstance(permalink_obj, str) else "",
        "link": str(link_obj) if isinstance(link_obj, str) else "",
    }
    return entry


def _write_catalog_files(module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any]) -> None:
    catalog_path = module_dir / "catalog.json"
    meta_path = module_dir / "catalog.meta.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.nyc_open_data"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    domain = str(getattr(BLUEPRINT, "DOMAIN", "data.cityofnewyork.us"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    headers = {"User-Agent": "sancho-nyc-open-data-discovery/1.0"}
    _kid, _ks = os.getenv("SODA_API_KEY_ID", "").strip(), os.getenv("SODA_API_KEY_SECRET", "").strip()
    if _kid and _ks:
        headers["Authorization"] = f"Basic {base64.b64encode(f'{_kid}:{_ks}'.encode()).decode()}"

    page_limit = 1000
    offset = 0
    total_results = 0
    all_results: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []

    while True:
        page, page_total, _, snapshot = _fetch_catalog_page(offset=offset, limit=page_limit, headers=headers)
        snapshots.append(snapshot)
        if snapshot.get("status") != "ok":
            break
        if offset == 0:
            total_results = page_total
        all_results.extend(page)
        if not page:
            break
        offset += page_limit
        if total_results and offset >= total_results:
            break
        if offset > 200000:
            raise RuntimeError("Exceeded safety offset while generating NYC catalog")

    failures = [item for item in snapshots if item.get("status") != "ok"]
    if failures:
        detail = "; ".join([f"{item.get('id')}: {item.get('error', 'unknown error')}" for item in failures])
        raise RuntimeError(f"NYC Open Data live catalog generation failed: {detail}")

    asset_entries = [_build_catalog_asset(item) for item in all_results]
    asset_entries = [item for item in asset_entries if item.get("id")]
    asset_entries.sort(key=lambda item: str(item.get("id", "")))

    dataset_ids = [str(item.get("id", "")) for item in asset_entries if bool(item.get("is_dataset_asset"))]
    non_dataset_asset_ids = [str(item.get("id", "")) for item in asset_entries if not bool(item.get("is_dataset_asset"))]
    live_dataset_ids = [str(item.get("id", "")) for item in asset_entries if bool(item.get("is_live_dataset"))]
    live_dataset_count = len(live_dataset_ids)

    category_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    datatype_counts: dict[str, int] = {}
    total_columns = 0
    for asset in asset_entries:
        total_columns += len(asset.get("columns", []))
        for category in asset.get("categories", []):
            category_counts[category] = category_counts.get(category, 0) + 1
        domain_category = str(asset.get("domain_category", "")).strip()
        if domain_category:
            category_counts[domain_category] = category_counts.get(domain_category, 0) + 1
        for tag in asset.get("tags", []) + asset.get("domain_tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for column in asset.get("columns", []):
            datatype = str(column.get("datatype", "")).strip()
            if datatype:
                datatype_counts[datatype] = datatype_counts.get(datatype, 0) + 1

    families = BLUEPRINT.build_families()
    indices = {
        "assets": asset_entries,
        "asset_ids": [str(item.get("id", "")) for item in asset_entries],
        "datasets": dataset_ids,
        "non_dataset_assets": non_dataset_asset_ids,
        "live_dataset_ids": live_dataset_ids,
        "categories": [{"name": key, "dataset_count": value} for key, value in sorted(category_counts.items())],
        "tags": [{"name": key, "dataset_count": value} for key, value in sorted(tag_counts.items())],
        "column_datatypes": [{"name": key, "column_count": value} for key, value in sorted(datatype_counts.items())],
    }

    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "domain": domain,
        "families": families,
        "indices": indices,
    }

    stats = {
        "family_count": len(families),
        "asset_count": len(asset_entries),
        "dataset_count": len(dataset_ids),
        "live_dataset_count": live_dataset_count,
        "non_dataset_asset_count": len(non_dataset_asset_ids),
        "column_count": total_columns,
        "assets_count": len(indices["assets"]),
        "asset_ids_count": len(indices["asset_ids"]),
        "datasets_count": len(indices["datasets"]),
        "non_dataset_assets_count": len(indices["non_dataset_assets"]),
        "live_dataset_ids_count": len(indices["live_dataset_ids"]),
        "categories_count": len(indices["categories"]),
        "tags_count": len(indices["tags"]),
        "column_datatypes_count": len(indices["column_datatypes"]),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [
                getattr(BLUEPRINT, "DOCS_OPEN_DATA_PORTAL", ""),
                getattr(BLUEPRINT, "DOCS_DISCOVERY_ENDPOINT", ""),
                getattr(BLUEPRINT, "DOCS_API_ENDPOINTS", ""),
                getattr(BLUEPRINT, "DOCS_QUERIES", ""),
                getattr(BLUEPRINT, "DOCS_QUERY_OPTION", ""),
                getattr(BLUEPRINT, "DOCS_APP_TOKENS", ""),
            ],
        },
    }

    _write_catalog_files(module_dir, catalog, meta)
    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "catalog": str(module_dir / "catalog.json"),
        "catalog_meta": str(module_dir / "catalog.meta.json"),
        "family_count": stats["family_count"],
        "asset_count": stats["asset_count"],
        "dataset_count": stats["dataset_count"],
        "live_dataset_count": stats["live_dataset_count"],
        "column_count": stats["column_count"],
        "status": "ok",
    }
