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


def fetch_socrata_dataset(
    *,
    runtime_http: dict[str, Any],
    app_token: str,
    domain: str,
    dataset_id: str,
    limit: int,
    where: str,
    extra_params: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> Any:
    params: dict[str, Any] = {"$limit": limit}
    if where:
        params["$where"] = where
    if extra_params:
        # Caller-supplied SoQL params win over our defaults.
        for key, value in extra_params.items():
            if value is None or value == "":
                continue
            params[key] = value

    headers: dict[str, str] = {}
    if env is not None:
        headers.update(_resolve_socrata_auth_headers(env))

    url = f"https://{domain}/resource/{dataset_id}.json"
    client = HttpClient(**runtime_http)
    return client.request_json("GET", url, params=params, headers=headers)
