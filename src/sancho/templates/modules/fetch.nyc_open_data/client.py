from __future__ import annotations

import csv
import io
from typing import Any

import requests

from sancho.runtime.http import HttpClient


def _prepare_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _request_text(
    *,
    method: str,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    json_body: dict[str, Any] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    response = requests.request(
        method=method,
        url=url,
        params=params or None,
        headers=headers or None,
        json=json_body if json_body else None,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    text = response.text
    rows: list[dict[str, Any]] = []
    if text.strip():
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(row) for row in reader]
    return {"content": text, "rows": rows}


def request_direct(
    *,
    runtime_http: dict[str, Any],
    method: str,
    base_url: str,
    path: str,
    params: dict[str, Any],
    json_body: dict[str, Any] | None,
    headers: dict[str, str] | None,
    response_mode: str,
) -> Any:
    url = _prepare_url(base_url, path)
    normalized_mode = response_mode.lower().strip()
    request_headers = headers or {}

    if normalized_mode in {"text", "csv"}:
        timeout_seconds = float(runtime_http.get("timeout_seconds", 20))
        return _request_text(
            method=method,
            url=url,
            params=params,
            headers=request_headers,
            json_body=json_body,
            timeout_seconds=timeout_seconds,
        )

    if normalized_mode == "json_or_text" and (path.endswith(".csv") or "export.csv" in path):
        timeout_seconds = float(runtime_http.get("timeout_seconds", 20))
        return _request_text(
            method=method,
            url=url,
            params=params,
            headers=request_headers,
            json_body=json_body,
            timeout_seconds=timeout_seconds,
        )

    client = HttpClient(**runtime_http)
    return client.request_json(
        method,
        url,
        params=params or None,
        headers=request_headers or None,
        json_body=json_body if json_body else None,
    )
