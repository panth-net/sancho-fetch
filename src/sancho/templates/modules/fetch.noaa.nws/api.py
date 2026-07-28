from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    headers = {"Accept": "application/geo+json, application/json"}
    client = HttpClient(**runtime_http)
    return client.request_json("GET", endpoint, params=params, headers=headers)
