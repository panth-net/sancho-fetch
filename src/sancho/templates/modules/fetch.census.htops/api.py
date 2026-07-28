from __future__ import annotations

from typing import Any

from sancho.runtime.net import get_json


def fetch_htops_rows(
    *,
    runtime_http: dict[str, Any],
    api_key: str,
    variables: list[str],
    time: str,
    geography: str,
    week: int | None,
) -> Any:
    # Always include WEEK so the caller can identify which weeks carry data.
    get_clause = ",".join(["WEEK", *(v for v in variables if v != "WEEK")])
    params: dict[str, Any] = {
        "get": get_clause,
        "for": geography,
        "time": time,
    }
    if week is not None:
        params["WEEK"] = str(week)
    if api_key:
        params["key"] = api_key

    url = "https://api.census.gov/data/timeseries/hps"
    timeout = float(runtime_http.get("timeout_seconds", 30))
    return get_json(url, params=params, timeout=timeout, max_retries=3)
