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
    headers: dict[str, str] = {}
    if api_token:
        headers["X-Api-Key"] = api_token

    client = HttpClient(**runtime_http)
    return client.request_json("GET", endpoint, params=params, headers=headers)
