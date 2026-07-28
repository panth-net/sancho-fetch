from __future__ import annotations

import base64
from typing import Any

from sancho.runtime.http import HttpClient


def _resolve_socrata_auth_headers(env: dict[str, str]) -> dict[str, str]:
    key_id = str(env.get("SODA_API_KEY_ID", "")).strip()
    key_secret = str(env.get("SODA_API_KEY_SECRET", "")).strip()
    if key_id and key_secret:
        credentials = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {}


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    api_token: str,
    endpoint: str,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
) -> Any:
    headers: dict[str, str] = {}
    if env is not None:
        headers.update(_resolve_socrata_auth_headers(env))

    client = HttpClient(**runtime_http)
    return client.request_json("GET", endpoint, params=params, headers=headers)
