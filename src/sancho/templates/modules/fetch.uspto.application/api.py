from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def _add_header_auth(*, headers: dict[str, str], env: dict[str, str], env_name: str, header_name: str) -> None:
    token = str(env.get(env_name, "")).strip()
    if token:
        headers[header_name] = token


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    env: dict[str, str],
    endpoint: str,
    params: dict[str, Any],
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> Any:
    """Call the USPTO Open Data Portal.

    Works for every endpoint under https://api.uspto.gov/api/v1/ :
    - GET `/patent/applications/{num}` (+ sub-paths: meta-data, continuity,
      assignment, attorney, foreign-priority, adjustment, transactions,
      documents, associated-documents)
    - GET/POST `/patent/applications/search`
    - GET/POST `/patent/status-codes`
    - GET/POST `/patent/trials/decisions/search` (PTAB)
    - GET/POST `/patent/trials/proceedings/search`
    - GET/POST `/patent/trials/documents/search`
    - GET/POST `/patent/petition/decisions/search`
    - GET `/datasets/products/search`, `/datasets/products/{id}`
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    _add_header_auth(
        headers=headers, env=env, env_name="USPTO_API_KEY", header_name="x-api-key",
    )

    client = HttpClient(**runtime_http)
    method_upper = method.upper()
    if method_upper == "POST":
        return client.request_json(
            "POST", endpoint, params=params or None, json=body or {}, headers=headers,
        )
    return client.request_json("GET", endpoint, params=params or None, headers=headers)
