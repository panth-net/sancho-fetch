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
    method: str,
    base_url: str,
    path: str,
    params: dict[str, Any],
    headers: dict[str, str] | None,
    response_mode: str,
    auth_query: dict[str, str] | None = None,
    http_client: HttpClient | None = None,
) -> Any:
    normalized_mode = response_mode.lower().strip()
    if normalized_mode != "json":
        raise ValueError(f"Unsupported response mode for fetch.fec: {response_mode}")

    request_params = dict(params)
    if auth_query:
        request_params.update(auth_query)

    requester = http_client or HttpClient(**runtime_http)
    return requester.request_json(
        method.upper().strip(),
        _prepare_url(base_url, path),
        params=request_params or None,
        headers=headers or None,
        json_body=None,
    )


def make_http_client(runtime_http: dict[str, Any]) -> HttpClient:
    return HttpClient(**runtime_http)
