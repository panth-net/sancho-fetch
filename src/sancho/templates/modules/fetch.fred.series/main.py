from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.data_store import (
    DEFAULT_CACHE_MAX_AGE_SECONDS,
    is_raw_cache_enabled,
    load_raw,
    resolve_staleness_seconds,
    save_raw,
)


MODULE_ID = "fetch.fred.series"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_fred_api")
    transform = _load_sibling("transform.py", "sancho_fetch_fred_transform")

    series_id = str(payload.get("series_id", "CPIAUCSL"))
    observation_start = str(payload.get("observation_start", "2020-01-01"))
    observation_end = str(payload.get("observation_end", ""))
    frequency = str(payload.get("frequency", "") or "")
    aggregation_method = str(payload.get("aggregation_method", "") or "")
    units = str(payload.get("units", "") or "")
    realtime_start = str(payload.get("realtime_start", "") or "")
    realtime_end = str(payload.get("realtime_end", "") or "")
    vintage_dates = str(payload.get("vintage_dates", "") or "")
    limit_obj = payload.get("limit")
    limit = int(limit_obj) if isinstance(limit_obj, (int, str)) and str(limit_obj).strip() else 100000
    offset_obj = payload.get("offset")
    offset = int(offset_obj) if isinstance(offset_obj, (int, str)) and str(offset_obj).strip() else None
    sort_order = str(payload.get("sort_order", "") or "")

    # Cache namespace must include any param that changes the API response,
    # otherwise different queries collide on the same cache key.
    cache_suffix_parts = [
        p for p in (frequency, aggregation_method, units, realtime_start, realtime_end,
                    vintage_dates, str(limit) if limit else "", str(offset) if offset else "",
                    sort_order)
        if p
    ]
    cache_suffix = "__".join(cache_suffix_parts) if cache_suffix_parts else ""
    family_or_dataset_id = f"{series_id}__{cache_suffix}" if cache_suffix else series_id
    source_url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "observation_start": observation_start,
        "observation_end": observation_end,
        "frequency": frequency,
        "aggregation_method": aggregation_method,
        "units": units,
        "realtime_start": realtime_start,
        "realtime_end": realtime_end,
        "vintage_dates": vintage_dates,
        "limit": limit,
        "offset": offset,
        "sort_order": sort_order,
    }
    max_age_seconds = resolve_staleness_seconds(
        payload=payload,
        runtime=context.runtime,
        module_id=MODULE_ID,
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload,
        runtime=context.runtime,
        module_id=MODULE_ID,
    )

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective_max_age_seconds = (
            max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        )
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id=MODULE_ID,
            family_or_dataset_id=family_or_dataset_id,
            params=params,
            source_url=source_url,
            max_age_seconds=effective_max_age_seconds,
        )
    if cached is not None:
        return transform.build_output(series_id=series_id, raw=cached.raw)

    raw = api.fetch_fred_series(
        runtime_http=context.runtime.get("http", {}),
        api_key=context.env.get("FRED_API_KEY", ""),
        series_id=series_id,
        observation_start=observation_start,
        observation_end=observation_end,
        frequency=frequency,
        aggregation_method=aggregation_method,
        units=units,
        realtime_start=realtime_start,
        realtime_end=realtime_end,
        vintage_dates=vintage_dates,
        limit=limit,
        offset=offset,
        sort_order=sort_order,
    )
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(series_id=series_id, raw=raw)
