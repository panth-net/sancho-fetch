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
    spec = importlib.util.spec_from_file_location("sancho_bls_catalog_blueprint", path)
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


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        results_obj = raw.get("Results")
        if isinstance(results_obj, dict):
            for key in ("series", "survey"):
                values = results_obj.get(key)
                if isinstance(values, list):
                    return values
        for key in ("results", "items", "data", "rows"):
            values = raw.get(key)
            if isinstance(values, list):
                return values
        return [raw]
    if isinstance(raw, list):
        return raw
    return []


def _request_get(url: str) -> tuple[Any, int]:
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "sancho-bls-discovery/1.0"},
    )
    response.raise_for_status()
    return response.json(), response.status_code


def _request_post(url: str, *, body: dict[str, Any]) -> tuple[Any, int]:
    response = requests.post(
        url,
        json=body,
        timeout=30,
        headers={"User-Agent": "sancho-bls-discovery/1.0"},
    )
    response.raise_for_status()
    return response.json(), response.status_code


def _fetch_surveys() -> tuple[list[Any], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "V2_BASE_URL", "https://api.bls.gov/publicAPI/v2"))
    path = "/surveys"
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        raw, status = _request_get(url)
        rows = _extract_rows(raw)
        return rows, _build_snapshot("v2.surveys.list", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("v2.surveys.list", url, status="error", count=0, http_status=0, error=str(exc))


def _fetch_series_sample() -> tuple[list[Any], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "V2_BASE_URL", "https://api.bls.gov/publicAPI/v2"))
    path = "/timeseries/data/"
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    body: dict[str, Any] = {"seriesid": ["CUUR0000SA0"], "latest": True}
    api_key = os.getenv("BLS_API_KEY", "").strip()
    if api_key:
        body["registrationkey"] = api_key
    try:
        raw, status = _request_post(url, body=body)
        rows = _extract_rows(raw)
        return rows, _build_snapshot("v2.timeseries.data", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("v2.timeseries.data", url, status="error", count=0, http_status=0, error=str(exc))


def _write_catalog_files(module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any]) -> None:
    catalog_path = module_dir / "catalog.json"
    meta_path = module_dir / "catalog.meta.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.bls"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs = [
        str(getattr(BLUEPRINT, "DOCS_HOME", "")),
        str(getattr(BLUEPRINT, "DOCS_SIGNATURE", "")),
    ]

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    surveys, surveys_snapshot = _fetch_surveys()
    sample_series, sample_series_snapshot = _fetch_series_sample()

    snapshots = [surveys_snapshot, sample_series_snapshot]
    failures = [item for item in snapshots if item.get("status") != "ok"]
    if failures:
        detail = "; ".join([f"{item.get('id')}: {item.get('error', 'unknown error')}" for item in failures])
        raise RuntimeError(f"BLS live catalog generation failed: {detail}")

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "indices": {
            "surveys": surveys,
            "sample_series": sample_series,
        },
    }
    stats = {
        "family_count": len(families),
        "surveys_count": len(surveys),
        "sample_series_count": len(sample_series),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": docs,
        },
    }

    _write_catalog_files(module_dir, catalog, meta)
    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "catalog": str(module_dir / "catalog.json"),
        "catalog_meta": str(module_dir / "catalog.meta.json"),
        "family_count": stats["family_count"],
        "surveys_count": stats["surveys_count"],
        "sample_series_count": stats["sample_series_count"],
        "status": "ok",
    }
