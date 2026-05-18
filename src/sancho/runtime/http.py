from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class CacheEntry:
    expires_at: float
    payload: Any


class HttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20,
        max_retries: int = 3,
        backoff_seconds: float = 0.4,
        rate_limit_per_second: float = 3,
        cache_ttl_seconds: int = 600,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.rate_limit_per_second = rate_limit_per_second
        self.cache_ttl_seconds = cache_ttl_seconds
        self._session = requests.Session()
        self._cache: dict[str, CacheEntry] = {}
        self._last_request_ts = 0.0

    def _apply_rate_limit(self) -> None:
        if self.rate_limit_per_second <= 0:
            return
        min_gap = 1.0 / self.rate_limit_per_second
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.monotonic() >= entry.expires_at:
            self._cache.pop(key, None)
            return None
        return entry.payload

    def _cache_put(self, key: str, payload: Any) -> None:
        ttl = max(0, self.cache_ttl_seconds)
        if ttl == 0:
            return
        self._cache[key] = CacheEntry(expires_at=time.monotonic() + ttl, payload=payload)

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        cache_key = f"{method.upper()}::{url}::{params or {}}::{json_body or {}}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._apply_rate_limit()
                response = self._session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=self.timeout_seconds,
                )
                self._last_request_ts = time.monotonic()
                response.raise_for_status()
                payload = response.json()
                self._cache_put(cache_key, payload)
                return payload
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (2**attempt))

        assert last_error is not None
        raise last_error
