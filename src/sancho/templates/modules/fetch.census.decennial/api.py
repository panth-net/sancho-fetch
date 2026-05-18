from __future__ import annotations

from typing import Any

from sancho.runtime.net import get_json


def fetch_decennial_rows(
    *,
    runtime_http: dict[str, Any],
    api_key: str,
    year: str,
    dataset: str,
    geography: str,
    variables: list[str],
    in_geography: str | None = None,
) -> Any:
    variable_clause = ",".join(variables)
    params: dict[str, Any] = {
        "get": variable_clause,
        "for": geography,
    }
    if in_geography:
        params["in"] = in_geography
    if api_key:
        params["key"] = api_key

    url = f"https://api.census.gov/data/{year}/dec/{dataset}"
    timeout = float(runtime_http.get("timeout_seconds", 30))
    return get_json(url, params=params, timeout=timeout, max_retries=3)
