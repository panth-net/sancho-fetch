from __future__ import annotations

from datetime import datetime
from typing import Any

from sancho.templates.runtime.data_store import (
    DEFAULT_CACHE_MAX_AGE_SECONDS,
    RawCacheRecord,
    is_raw_cache_enabled,
    load_raw,
    resolve_staleness_seconds,
    save_raw,
)


def save_raw_with_context(
    context: Any,
    module_id: str,
    dataset_id: str,
    data: Any,
    meta: dict[str, Any] | None = None,
    *,
    fetched_at: str | None = None,
    now: datetime | None = None,
) -> Any:
    return save_raw(context, module_id, dataset_id, data, meta, fetched_at=fetched_at, now=now)


def load_raw_with_context(
    context: Any,
    module_id: str,
    dataset_id: str,
    max_age_seconds: int | float | None = None,
    *,
    now: datetime | None = None,
) -> Any | None:
    return load_raw(context, module_id, dataset_id, max_age_seconds=max_age_seconds, now=now)


__all__ = [
    "DEFAULT_CACHE_MAX_AGE_SECONDS",
    "RawCacheRecord",
    "is_raw_cache_enabled",
    "save_raw",
    "load_raw",
    "save_raw_with_context",
    "load_raw_with_context",
    "resolve_staleness_seconds",
]
