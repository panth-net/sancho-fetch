from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def _prepare_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _inject_auth_body(
    *,
    body: dict[str, Any],
    env: dict[str, str],
    auth_body: dict[str, str],
) -> dict[str, Any]:
    values = dict(body)
    for field_name, env_name in auth_body.items():
        token = str(env.get(env_name, "")).strip()
        if token:
            values[field_name] = token
    return values


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
    auth_body: dict[str, str] | None = None,
) -> Any:
    url = _prepare_url(base_url, path)
    normalized_method = method.upper().strip()
    normalized_mode = response_mode.lower().strip()

    if normalized_mode != "json":
        raise ValueError(f"Unsupported response mode for fetch.bls: {response_mode}")

    request_query: dict[str, Any] = {}
    request_body: dict[str, Any] | None = None
    if normalized_method in {"POST", "PUT", "PATCH"}:
        request_body = dict(json_body or {})
        if not request_body and params:
            request_body = dict(params)
    else:
        request_query = dict(params)

    if request_body is not None and auth_body:
        request_body = _inject_auth_body(body=request_body, env=env, auth_body=auth_body)

    client = HttpClient(**runtime_http)
    return client.request_json(
        normalized_method,
        url,
        params=request_query or None,
        headers=headers or None,
        json_body=request_body,
    )
