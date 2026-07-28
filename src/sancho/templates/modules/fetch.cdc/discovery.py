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
    spec = importlib.util.spec_from_file_location("sancho_cdc_catalog_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BLUEPRINT = _load_blueprint()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_snapshot(
    source_id: str,
    url: str,
    *,
    status: str,
    count: int,
    http_status: int,
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
    if error:
        payload["error"] = error
    return payload


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


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("results", "views", "items", "data", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return [raw]
    return []


def _fetch_catalog_sample(headers: dict[str, str]) -> tuple[list[Any], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "CDC_PORTAL_BASE_URL", "https://data.cdc.gov"))
    path = "/api/views"
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        raw, status = _request_json(url, params={"$limit": 10, "$offset": 0}, headers=headers)
        rows = _extract_rows(raw)
        return rows, _build_snapshot("portal.datasets.list", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("portal.datasets.list", url, status="error", count=0, http_status=0, error=str(exc))


def _fetch_dataset_sample(headers: dict[str, str]) -> tuple[list[Any], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "CDC_RESOURCE_BASE_URL", "https://data.cdc.gov/resource"))
    path = "/bi63-dtpu.json"
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        raw, status = _request_json(url, params={"$limit": 10, "$offset": 0}, headers=headers)
        rows = _extract_rows(raw)
        return rows, _build_snapshot("resource.leading_death", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("resource.leading_death", url, status="error", count=0, http_status=0, error=str(exc))


def _write_catalog_files(module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any]) -> None:
    catalog_path = module_dir / "catalog.json"
    meta_path = module_dir / "catalog.meta.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.cdc"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    headers = {"User-Agent": "sancho-cdc-discovery/1.0"}
    key_id = os.getenv("SODA_API_KEY_ID", "").strip()
    key_secret = os.getenv("SODA_API_KEY_SECRET", "").strip()
    if key_id and key_secret:
        import base64
        credentials = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"

    catalog_sample, catalog_snapshot = _fetch_catalog_sample(headers)
    dataset_sample, dataset_snapshot = _fetch_dataset_sample(headers)

    snapshots = [catalog_snapshot, dataset_snapshot]
    failures = [item for item in snapshots if item.get("status") != "ok"]
    if failures:
        detail = "; ".join([f"{item.get('id')}: {item.get('error', 'unknown error')}" for item in failures])
        raise RuntimeError(f"CDC live catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "indices": {
            "catalog_sample": catalog_sample,
            "leading_death_sample": dataset_sample,
        },
    }
    stats = {
        "family_count": len(families),
        "catalog_sample_count": len(catalog_sample),
        "leading_death_sample_count": len(dataset_sample),
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
                str(getattr(BLUEPRINT, "DOCS_CDC_PORTAL", "")),
                str(getattr(BLUEPRINT, "DOCS_API_ENDPOINTS", "")),
                str(getattr(BLUEPRINT, "DOCS_QUERIES", "")),
                str(getattr(BLUEPRINT, "DOCS_APP_TOKENS", "")),
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
        "catalog_sample_count": stats["catalog_sample_count"],
        "leading_death_sample_count": stats["leading_death_sample_count"],
        "status": "ok",
    }
