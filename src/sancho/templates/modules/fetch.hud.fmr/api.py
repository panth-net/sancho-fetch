from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def fetch_hud_data(
    *,
    runtime_http: dict[str, Any],
    api_token: str,
    url: str,
    query: dict[str, Any],
) -> Any:
    headers: dict[str, str] = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    client = HttpClient(**runtime_http)
    return client.request_json("GET", url, params=query, headers=headers)
