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
    spec = importlib.util.spec_from_file_location("sancho_fec_catalog_blueprint", path)
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


def _request_json(url: str, *, params: dict[str, Any] | None = None) -> tuple[Any, int]:
    response = requests.get(
        url,
        params=params or None,
        timeout=45,
        headers={"User-Agent": "sancho-fec-discovery/1.0"},
    )
    response.raise_for_status()
    return response.json(), response.status_code


def _request_text(url: str) -> tuple[str, int]:
    response = requests.get(
        url,
        timeout=45,
        headers={"User-Agent": "sancho-fec-discovery/1.0"},
    )
    response.raise_for_status()
    return response.text, response.status_code


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("results", "items", "data", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return [raw]
    return []


def _fetch_swagger() -> tuple[dict[str, Any], dict[str, Any]]:
    url = str(getattr(BLUEPRINT, "DOCS_SWAGGER", "https://api.open.fec.gov/swagger/"))
    try:
        payload, status = _request_json(url)
        path_count = len(payload.get("paths", {})) if isinstance(payload, dict) else 0
        summary = {"path_count": path_count}
        if isinstance(payload, dict):
            summary["swagger"] = payload
        return summary, _build_snapshot("docs.swagger", url, status="ok", count=path_count, http_status=status)
    except Exception as exc:
        return {}, _build_snapshot("docs.swagger", url, status="error", count=0, http_status=0, error=str(exc))


def _fetch_developers() -> tuple[dict[str, Any], dict[str, Any]]:
    url = str(getattr(BLUEPRINT, "DOCS_DEVELOPERS", "https://api.open.fec.gov/developers/"))
    try:
        text, status = _request_text(url)
        return {"chars": len(text)}, _build_snapshot("docs.developers", url, status="ok", count=1, http_status=status)
    except Exception as exc:
        return {}, _build_snapshot("docs.developers", url, status="error", count=0, http_status=0, error=str(exc))


def _fetch_candidates_sample() -> tuple[list[Any], dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "FEC_BASE_URL", "https://api.open.fec.gov/v1"))
    url = f"{base_url.rstrip('/')}/candidates/search/"
    api_key = os.getenv("DATA_GOV_API_KEY", "").strip()
    if not api_key:
        return [], _build_snapshot("v1.candidates.search", url, status="skipped", count=0, http_status=0, error="missing DATA_GOV_API_KEY")
    try:
        raw, status = _request_json(url, params={"api_key": api_key, "q": "smith", "per_page": 5, "page": 1})
        rows = _extract_rows(raw)
        return rows, _build_snapshot("v1.candidates.search", url, status="ok", count=len(rows), http_status=status)
    except Exception as exc:
        return [], _build_snapshot("v1.candidates.search", url, status="error", count=0, http_status=0, error=str(exc))


def _write_catalog_files(module_dir: Path, catalog: dict[str, Any], meta: dict[str, Any]) -> None:
    catalog_path = module_dir / "catalog.json"
    meta_path = module_dir / "catalog.meta.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.fec"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    swagger_payload, swagger_snapshot = _fetch_swagger()
    developers_payload, developers_snapshot = _fetch_developers()
    candidates_sample, candidates_snapshot = _fetch_candidates_sample()
    snapshots = [swagger_snapshot, developers_snapshot, candidates_snapshot]

    required_failures = [
        item for item in (swagger_snapshot, developers_snapshot) if item.get("status") != "ok"
    ]
    if required_failures:
        detail = "; ".join([f"{item.get('id')}: {item.get('error', 'unknown error')}" for item in required_failures])
        raise RuntimeError(f"FEC live catalog generation failed: {detail}")

    swagger = swagger_payload.get("swagger") if isinstance(swagger_payload, dict) else None
    if not isinstance(swagger, dict):
        raise RuntimeError("FEC live catalog generation failed: Swagger payload was not a JSON object")

    families = BLUEPRINT.build_families(swagger)
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "indices": {
            "super_pac_workflows": list(getattr(BLUEPRINT, "SUPER_PAC_WORKFLOWS", [])),
            "candidates_sample": candidates_sample,
            "discovery_docs": {
                "swagger": {"path_count": swagger_payload.get("path_count", len(families))},
                "developers": developers_payload,
            },
        },
        "notices": {
            "contributor_usage": {
                "message": "FEC individual contributor information has legal limits around sale, solicitation, and commercial use.",
                "source": str(getattr(BLUEPRINT, "CONTRIBUTOR_USAGE_URL", "")),
            }
        },
    }
    stats = {
        "family_count": len(families),
        "swagger_path_count": int(swagger_payload.get("path_count", len(families))),
        "super_pac_workflow_count": len(getattr(BLUEPRINT, "SUPER_PAC_WORKFLOWS", [])),
        "candidates_sample_count": len(candidates_sample),
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
                str(getattr(BLUEPRINT, "DOCS_DEVELOPERS", "")),
                str(getattr(BLUEPRINT, "DOCS_SWAGGER", "")),
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
        "candidates_sample_count": stats["candidates_sample_count"],
        "status": "ok",
    }
