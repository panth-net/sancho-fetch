from __future__ import annotations

from typing import Any

from sancho.runtime.net import get_json


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

    timeout = float(runtime_http.get("timeout_seconds", 30))
    return get_json(endpoint, params=query, timeout=timeout, max_retries=3)
