from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    dataset: str,
    filters: dict[str, Any],
    lang: str,
) -> Any:
    # Override timeout: large Eurostat extractions are intermittently slow.
    http_config = {**runtime_http, "timeout_seconds": 60, "max_retries": 4}
    client = HttpClient(**http_config)
    params: dict[str, Any] = {"format": "JSON", "lang": lang}
    for key, value in filters.items():
        params[str(key)] = value
    return client.request_json("GET", f"{BASE_URL}/{dataset}", params=params)
