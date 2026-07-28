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


def request_direct(
    *,
    runtime_http: dict[str, Any],
    method: str,
    base_url: str,
    path: str,
    params: dict[str, Any],
    headers: dict[str, str] | None,
    response_mode: str,
) -> Any:
    url = _prepare_url(base_url, path)
    if response_mode == "text":
        timeout = float(runtime_http.get("timeout_seconds", 20))
        response = requests.request(
            method=method,
            url=url,
            params=params or None,
            headers=headers or None,
            timeout=timeout,
        )
        response.raise_for_status()
        text = response.text
        rows: list[dict[str, Any]] = []
        if text.strip():
            reader = csv.DictReader(io.StringIO(text))
            rows = [dict(row) for row in reader]
        return {"content": text, "rows": rows}

    client = HttpClient(**runtime_http)
    return client.request_json(
        method,
        url,
        params=params or None,
        headers=headers or None,
        json_body=None,
    )
