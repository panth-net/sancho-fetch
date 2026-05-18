from __future__ import annotations

from typing import Any


FEC_MAX_PER_PAGE = 100
DEFAULT_PAGE_SIZE = FEC_MAX_PER_PAGE
MAX_ESTIMATE_FOR_NOTICE = 100_000


def normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("pagination", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("payload.pagination must be an object when provided")

    mode = str(raw.get("mode", "single")).strip().lower() or "single"
    if mode not in {"single", "pages", "all"}:
        raise ValueError("pagination.mode must be one of: single, pages, all")
    if mode == "all" and not bool(raw.get("confirmed", False)):
        raise ValueError("pagination.mode='all' requires pagination.confirmed=true")

    max_pages = _positive_int(raw.get("max_pages"))
    max_records = _positive_int(raw.get("max_records"))
    if mode == "pages" and max_pages is None and max_records is None:
        raise ValueError("pagination.mode='pages' requires max_pages or max_records")

    page_size = _page_size(raw.get("page_size", raw.get("per_page")))

    return {
        "mode": mode,
        "max_pages": max_pages,
        "max_records": max_records,
        "confirmed": bool(raw.get("confirmed", False)),
        "page_size": page_size,
        "maximize_per_page": bool(raw.get("maximize_per_page", True)),
    }


def apply_page_size(
    params: dict[str, Any],
    *,
    family: dict[str, Any],
    config: dict[str, Any],
    explicit_per_page: bool,
) -> dict[str, Any]:
    query_params = family.get("query_params", {})
    if not isinstance(query_params, dict) or "per_page" not in query_params:
        return params
    if explicit_per_page:
        return params

    page_size = config.get("page_size")
    if not isinstance(page_size, int):
        if not bool(config.get("maximize_per_page", True)):
            return params
        page_size = FEC_MAX_PER_PAGE

    out = dict(params)
    out["per_page"] = min(page_size, FEC_MAX_PER_PAGE)
    return out


def fetch(
    *,
    client: Any,
    runtime_http: dict[str, Any],
    method: str,
    base_url: str,
    path: str,
    params: dict[str, Any],
    headers: dict[str, str],
    response_mode: str,
    auth_query: dict[str, str],
    config: dict[str, Any],
) -> Any:
    if config.get("mode") == "single":
        return client.request_direct(
            runtime_http=runtime_http,
            method=method,
            base_url=base_url,
            path=path,
            params=params,
            headers=headers,
            response_mode=response_mode,
            auth_query=auth_query,
        )

    combined_rows: list[Any] = []
    pages: list[dict[str, Any]] = []
    current_params = dict(params)
    first_raw: Any | None = None
    last_raw: Any | None = None
    stop_reason = "complete"
    http_client = client.make_http_client(runtime_http)

    while True:
        raw = client.request_direct(
            runtime_http=runtime_http,
            method=method,
            base_url=base_url,
            path=path,
            params=current_params,
            headers=headers,
            response_mode=response_mode,
            auth_query=auth_query,
            http_client=http_client,
        )
        if first_raw is None:
            first_raw = raw
        last_raw = raw

        rows = extract_rows(raw)
        remaining = _remaining_record_slots(config, len(combined_rows))
        if remaining is not None and len(rows) > remaining:
            rows = rows[:remaining]
            stop_reason = "max_records"
        combined_rows.extend(rows)
        provider_pagination = provider_pagination_from(raw)
        pages.append({
            "params": dict(current_params),
            "row_count": len(rows),
            "provider_pagination": provider_pagination,
        })

        if stop_reason == "max_records":
            break
        if _remaining_record_slots(config, len(combined_rows)) == 0:
            stop_reason = "max_records"
            break
        if _hit_page_limit(config, len(pages)):
            stop_reason = "max_pages"
            break
        next_params = next_page_params(current_params, provider_pagination, len(rows))
        if next_params is None:
            break
        current_params = next_params

    return combine_raw(
        first_raw=first_raw,
        last_raw=last_raw,
        rows=combined_rows,
        pages=pages,
        config=config,
        stop_reason=stop_reason,
        next_params=next_page_params(
            current_params,
            provider_pagination_from(last_raw),
            len(extract_rows(last_raw)),
        ) if last_raw is not None else None,
    )


def extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("results", "items", "data", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return [raw]
    return []


def provider_pagination_from(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    pagination = raw.get("pagination")
    return pagination if isinstance(pagination, dict) else {}


def summarize(raw: Any, *, params: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("sancho_pagination"), dict):
        return raw["sancho_pagination"]

    rows = extract_rows(raw)
    provider_pagination = provider_pagination_from(raw)
    next_params = next_page_params(params, provider_pagination, len(rows))
    count = _int_or_none(provider_pagination.get("count"))
    pages = _int_or_none(provider_pagination.get("pages"))
    current_page = _int_or_none(provider_pagination.get("page")) or _int_or_none(params.get("page")) or 1
    per_page = _int_or_none(provider_pagination.get("per_page")) or _int_or_none(params.get("per_page")) or DEFAULT_PAGE_SIZE
    has_more = next_params is not None
    remaining_pages = max(0, pages - current_page) if pages is not None else None

    return {
        "mode": config.get("mode", "single"),
        "fetched_pages": 1,
        "fetched_rows": len(rows),
        "has_more": has_more,
        "provider_count": count,
        "provider_count_is_exact": provider_pagination.get("is_count_exact"),
        "estimated_total_pages": pages,
        "per_page": per_page,
        "current_page": current_page,
        "next_params": next_params,
        "estimated_remaining_api_calls": remaining_pages if has_more else 0,
        "large_result_notice": _large_notice(count, pages),
        "stop_reason": "single_page",
    }


def next_page_params(
    params: dict[str, Any],
    provider_pagination: dict[str, Any],
    row_count: int,
) -> dict[str, Any] | None:
    if not provider_pagination:
        return None

    last_indexes = provider_pagination.get("last_indexes")
    if isinstance(last_indexes, dict) and last_indexes:
        next_params = dict(params)
        next_params.update(last_indexes)
        return next_params
    if "last_indexes" in provider_pagination or "last_index" in params:
        return None

    page = _int_or_none(provider_pagination.get("page")) or _int_or_none(params.get("page"))
    if page is None:
        return None
    pages = _int_or_none(provider_pagination.get("pages"))
    per_page = _int_or_none(provider_pagination.get("per_page")) or _int_or_none(params.get("per_page"))
    if pages is not None:
        if page >= pages:
            return None
    elif per_page is None or row_count < per_page:
        return None

    next_params = dict(params)
    next_params["page"] = page + 1
    return next_params


def combine_raw(
    *,
    first_raw: Any | None,
    last_raw: Any | None,
    rows: list[Any],
    pages: list[dict[str, Any]],
    config: dict[str, Any],
    stop_reason: str,
    next_params: dict[str, Any] | None,
) -> dict[str, Any]:
    base = dict(first_raw) if isinstance(first_raw, dict) else {}
    provider_pagination = provider_pagination_from(last_raw)
    base["results"] = rows
    base["pagination"] = provider_pagination
    base["sancho_pages"] = pages
    base["sancho_pagination"] = {
        "mode": config.get("mode", "single"),
        "fetched_pages": len(pages),
        "fetched_rows": len(rows),
        "has_more": next_params is not None,
        "provider_count": _int_or_none(provider_pagination.get("count")),
        "provider_count_is_exact": provider_pagination.get("is_count_exact"),
        "estimated_total_pages": _int_or_none(provider_pagination.get("pages")),
        "per_page": _int_or_none(provider_pagination.get("per_page")),
        "next_params": next_params,
        "estimated_remaining_api_calls": _remaining_calls(provider_pagination, next_params),
        "large_result_notice": _large_notice(
            _int_or_none(provider_pagination.get("count")),
            _int_or_none(provider_pagination.get("pages")),
        ),
        "stop_reason": stop_reason,
    }
    return base


def _positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _page_size(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == "max":
        return FEC_MAX_PER_PAGE
    number = _positive_int(value)
    if number is None:
        raise ValueError("pagination.page_size must be a positive integer or 'max'")
    if number > FEC_MAX_PER_PAGE:
        raise ValueError(f"pagination.page_size must be <= {FEC_MAX_PER_PAGE} for FEC")
    return number


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hit_page_limit(config: dict[str, Any], page_count: int) -> bool:
    max_pages = config.get("max_pages")
    return isinstance(max_pages, int) and page_count >= max_pages


def _remaining_record_slots(config: dict[str, Any], current_rows: int) -> int | None:
    max_records = config.get("max_records")
    if not isinstance(max_records, int):
        return None
    return max(0, max_records - current_rows)


def _remaining_calls(provider_pagination: dict[str, Any], next_params: dict[str, Any] | None) -> int | None:
    if next_params is None:
        return 0
    page = _int_or_none(provider_pagination.get("page"))
    pages = _int_or_none(provider_pagination.get("pages"))
    if page is None or pages is None:
        return None
    return max(0, pages - page)


def _large_notice(count: int | None, pages: int | None) -> str:
    if (count is not None and count >= MAX_ESTIMATE_FOR_NOTICE) or (pages is not None and pages >= 1000):
        return (
            "This FEC request may contain a very large result set. "
            "Narrow filters or request a bounded page/record count before fetching everything."
        )
    return ""
