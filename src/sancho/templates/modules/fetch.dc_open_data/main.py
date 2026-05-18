from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.http import HttpClient
from sancho.runtime.public_source import run_public_source
from sancho.runtime.transform_rows import extract_rows


CONFIG = {
    "module_id": "fetch.dc_open_data",
    "dataset_ref": "dc_open_data_service_requests",
    "default_endpoint": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/ServiceRequests/FeatureServer/13/query",
    "default_params": {
        "f": "json",
        "where": "1=1",
        "outFields": (
            "SERVICEREQUESTID,SERVICECODEDESCRIPTION,"
            "SERVICETYPECODEDESCRIPTION,SERVICEORDERDATE,WARD,STATUS_CODE"
        ),
        "orderByFields": "SERVICEORDERDATE DESC",
        "resultRecordCount": 1000,
        "returnGeometry": "false",
    },
    "default_mode": "json",
    "default_search": None,
    "default_limit": None,
    "preferred_keys": ["features"],
}


def _metadata_endpoint(endpoint: str) -> str:
    cleaned = endpoint.rstrip("/")
    if cleaned.lower().endswith("/query"):
        return cleaned[: -len("/query")]
    return cleaned


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _flatten_rows(raw: Any) -> list[dict[str, Any]]:
    rows = extract_rows(raw, preferred_keys=tuple(CONFIG["preferred_keys"]))
    if rows and isinstance(rows[0], dict) and isinstance(rows[0].get("attributes"), dict):
        return [row["attributes"] for row in rows if isinstance(row, dict)]
    return [row for row in rows if isinstance(row, dict)]


def _shape(rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = sorted({key for row in rows for key in row.keys()})
    return {
        "row_count": len(rows),
        "columns": columns,
        "sample_row": rows[0] if rows else {},
    }


def _pagination_mode(payload: dict[str, Any]) -> tuple[str, int | None]:
    pagination = payload.get("pagination")
    pagination_obj = pagination if isinstance(pagination, dict) else {}
    mode = str(
        pagination_obj.get("mode")
        or payload.get("pagination_mode")
        or "all"
    ).strip().lower()
    max_pages = _int_or_none(pagination_obj.get("max_pages") or payload.get("max_pages"))
    if mode not in {"all", "pages", "single"}:
        mode = "all"
    if mode == "single":
        max_pages = 1
    if mode == "pages" and max_pages is None:
        max_pages = 1
    return mode, max_pages


def _run_arcgis_json(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    endpoint = str(payload.get("endpoint") or CONFIG["default_endpoint"])
    params = dict(CONFIG["default_params"])
    payload_params = payload.get("params")
    if isinstance(payload_params, dict):
        params.update(payload_params)
    params["f"] = "json"
    params.setdefault("returnGeometry", "false")

    runtime_http = context.runtime.get("http", {})
    client = HttpClient(**runtime_http)

    metadata_raw = client.request_json("GET", _metadata_endpoint(endpoint), params={"f": "json"})
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    max_record_count = _int_or_none(metadata.get("maxRecordCount")) or 1000
    supports_pagination = bool(
        metadata.get("supportsPagination")
        or (
            isinstance(metadata.get("advancedQueryCapabilities"), dict)
            and metadata["advancedQueryCapabilities"].get("supportsPagination")
        )
    )

    explicit_page_size = _int_or_none(payload.get("page_size"))
    requested_page_size = explicit_page_size or _int_or_none(params.get("resultRecordCount")) or max_record_count
    page_size = max(1, min(requested_page_size, max_record_count))

    max_records = _int_or_none(payload.get("max_records"))
    if max_records is None and "limit" in payload:
        max_records = _int_or_none(payload.get("limit"))
    if max_records is not None:
        page_size = min(page_size, max_records)

    count_params = dict(params)
    count_params.pop("resultOffset", None)
    count_params.pop("resultRecordCount", None)
    count_params["returnCountOnly"] = "true"
    count_raw = client.request_json("GET", endpoint, params=count_params)
    total_count = _int_or_none(count_raw.get("count")) if isinstance(count_raw, dict) else None

    mode, max_pages = _pagination_mode(payload)
    rows: list[dict[str, Any]] = []
    first_page_raw: Any = None
    fetched_pages = 0
    offset = _int_or_none(params.get("resultOffset")) or 0
    next_offset: int | None = offset
    stop_reason = "complete"

    while True:
        if max_records is not None and len(rows) >= max_records:
            stop_reason = "max_records"
            break
        if max_pages is not None and fetched_pages >= max_pages:
            stop_reason = "max_pages"
            break
        if total_count is not None and offset >= total_count:
            stop_reason = "complete"
            break

        current_page_size = page_size
        if max_records is not None:
            current_page_size = min(current_page_size, max_records - len(rows))
        if current_page_size <= 0:
            stop_reason = "max_records"
            break

        page_params = dict(params)
        page_params["resultOffset"] = offset
        page_params["resultRecordCount"] = current_page_size
        page_params.pop("returnCountOnly", None)
        raw_page = client.request_json("GET", endpoint, params=page_params)
        if first_page_raw is None:
            first_page_raw = raw_page
        page_rows = _flatten_rows(raw_page)
        fetched_pages += 1
        rows.extend(page_rows)
        next_offset = offset + len(page_rows)

        if max_records is not None and len(rows) >= max_records:
            rows = rows[:max_records]
            stop_reason = "max_records"
            break
        if not supports_pagination or mode == "single":
            stop_reason = "single_page" if mode == "single" else "no_pagination"
            break
        if len(page_rows) < current_page_size:
            stop_reason = "complete"
            break
        if isinstance(raw_page, dict) and raw_page.get("exceededTransferLimit") is False and total_count is None:
            stop_reason = "complete"
            break

        offset = next_offset
        if not page_rows:
            stop_reason = "complete"
            break

    has_more = False
    if stop_reason in {"max_pages", "max_records", "single_page", "no_pagination"}:
        if total_count is None:
            has_more = bool(rows)
        else:
            has_more = len(rows) < total_count

    return {
        "dataset_ref": CONFIG["dataset_ref"],
        "endpoint": endpoint,
        "params": params,
        "mode": "json",
        "rows": rows,
        "raw": {
            "metadata": metadata,
            "count": count_raw,
            "first_page": first_page_raw,
        },
        "pagination": {
            "mode": mode,
            "supports_pagination": supports_pagination,
            "page_size": page_size,
            "max_record_count": max_record_count,
            "total_count": total_count,
            "fetched_pages": fetched_pages,
            "fetched_rows": len(rows),
            "has_more": has_more,
            "next_offset": next_offset if has_more else None,
            "stop_reason": stop_reason,
            "rate_limit_per_second": runtime_http.get("rate_limit_per_second", 3),
            "rate_limit_source": (
                "No DC-specific public limit found; uses Sancho HttpClient "
                "throttling, retries, and max-sized ArcGIS pages."
            ),
        },
        "shape": _shape(rows),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or CONFIG.get("default_mode", "json")).strip().lower()
    if mode == "html_links":
        return run_public_source(context=context, payload=payload, config=CONFIG)
    return _run_arcgis_json(context=context, payload=payload)
