from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    api_token: str,
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    query = dict(params)
    if api_token:
        query["api_key"] = api_token

    client = HttpClient(**runtime_http)
    return client.request_json("GET", endpoint, params=query)
