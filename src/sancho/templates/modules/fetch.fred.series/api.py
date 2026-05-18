from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def fetch_fred_series(
    *,
    runtime_http: dict[str, Any],
    api_key: str,
    series_id: str,
    observation_start: str,
    observation_end: str,
    frequency: str = "",
    aggregation_method: str = "",
    units: str = "",
    realtime_start: str = "",
    realtime_end: str = "",
    vintage_dates: str = "",
    limit: int | None = None,
    offset: int | None = None,
    sort_order: str = "",
) -> Any:
    params: dict[str, Any] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
    }
    if observation_end:
        params["observation_end"] = observation_end
    if frequency:
        params["frequency"] = frequency
    if aggregation_method:
        params["aggregation_method"] = aggregation_method
    if units:
        params["units"] = units
    if realtime_start:
        params["realtime_start"] = realtime_start
    if realtime_end:
        params["realtime_end"] = realtime_end
    if vintage_dates:
        params["vintage_dates"] = vintage_dates
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if sort_order:
        params["sort_order"] = sort_order

    client = HttpClient(**runtime_http)
    return client.request_json(
        "GET",
        "https://api.stlouisfed.org/fred/series/observations",
        params=params,
    )
