from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def _add_query_auth(*, query: dict[str, Any], env: dict[str, str], env_name: str, query_param: str) -> None:
    token = str(env.get(env_name, "")).strip()
    if token:
        query[query_param] = token


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    env: dict[str, str],
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    query = dict(params)
    query.setdefault("format", "application/json")

    _add_query_auth(query=query, env=env, env_name="AIRNOW_API_KEY", query_param="API_KEY")

    client = HttpClient(**runtime_http)
    return client.request_json("GET", endpoint, params=query)
