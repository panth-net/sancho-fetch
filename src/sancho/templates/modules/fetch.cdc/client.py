from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def _prepare_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def request_direct(
    *,
    runtime_http: dict[str, Any],
    env: dict[str, str],
    method: str,
    base_url: str,
    path: str,
    params: dict[str, Any],
    json_body: dict[str, Any] | None,
    headers: dict[str, str] | None,
    response_mode: str,
) -> Any:
    normalized_mode = response_mode.lower().strip()
    if normalized_mode != "json":
        raise ValueError(f"Unsupported response mode for fetch.cdc: {response_mode}")

    url = _prepare_url(base_url, path)
    request_headers = dict(headers or {})
    if "Authorization" not in request_headers:
        key_id = str(env.get("SODA_API_KEY_ID", "")).strip()
        key_secret = str(env.get("SODA_API_KEY_SECRET", "")).strip()
        if key_id and key_secret:
            import base64
            credentials = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
            request_headers["Authorization"] = f"Basic {credentials}"

    normalized_method = method.upper().strip()
    request_query = dict(params)
    request_body = dict(json_body or {})
    if normalized_method in {"POST", "PUT", "PATCH"}:
        if not request_body and request_query:
            request_body = dict(request_query)
            request_query = {}
    else:
        request_body = {}

    client = HttpClient(**runtime_http)
    return client.request_json(
        normalized_method,
        url,
        params=request_query or None,
        headers=request_headers or None,
        json_body=request_body or None,
    )
