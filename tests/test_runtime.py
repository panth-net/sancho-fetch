from __future__ import annotations

from typing import Any

import pytest

from sancho.runtime.http import HttpClient
from sancho.runtime.schema import validate_schema


class _Resp:
    def __init__(self, payload: Any):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_http_client_retry_and_cache(monkeypatch) -> None:
    attempts = {"count": 0}

    def fake_request(method, url, params=None, headers=None, json=None, timeout=20):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient")
        return _Resp({"ok": True, "url": url})

    client = HttpClient(max_retries=1, backoff_seconds=0, cache_ttl_seconds=60, rate_limit_per_second=100)
    monkeypatch.setattr(client, "_session", type("S", (), {"request": staticmethod(fake_request)})())

    first = client.request_json("GET", "https://example.com")
    second = client.request_json("GET", "https://example.com")

    assert first["ok"] is True
    assert second["ok"] is True
    assert attempts["count"] == 2


def test_schema_validation_raises_on_missing_required() -> None:
    with pytest.raises(Exception):
        validate_schema({"a": 1}, {"type": "object", "required": ["a", "b"]})
