from __future__ import annotations

from typing import Any


def parse_age_seconds(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 0:
            return False
        if value == 1:
            return True
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def resolve_staleness_seconds(
    *,
    payload: dict[str, Any],
    runtime: dict[str, Any],
    module_id: str,
    default_seconds: int | float | None = None,
) -> int | None:
    payload_cache = payload.get("cache", {})
    runtime_cache = runtime.get("raw_cache", {})
    module_runtime_cache = runtime_cache.get("modules", {}).get(module_id, {})

    candidates = [
        payload.get("cache_max_age_seconds"),
        payload.get("staleness_seconds"),
        payload_cache.get("max_age_seconds") if isinstance(payload_cache, dict) else None,
        payload_cache.get("staleness_seconds") if isinstance(payload_cache, dict) else None,
        module_runtime_cache.get("max_age_seconds") if isinstance(module_runtime_cache, dict) else None,
        module_runtime_cache.get("staleness_seconds") if isinstance(module_runtime_cache, dict) else None,
        runtime_cache.get("max_age_seconds") if isinstance(runtime_cache, dict) else None,
        runtime_cache.get("staleness_seconds") if isinstance(runtime_cache, dict) else None,
        runtime.get("raw_cache_max_age_seconds"),
    ]

    for candidate in candidates:
        parsed = parse_age_seconds(candidate)
        if parsed is not None:
            return max(0, int(parsed))

    parsed_default = parse_age_seconds(default_seconds)
    if parsed_default is None:
        return None
    return max(0, int(parsed_default))


def is_raw_cache_enabled(
    *,
    payload: dict[str, Any],
    runtime: dict[str, Any],
    module_id: str,
    default_enabled: bool = False,
) -> bool:
    payload_cache = payload.get("cache", {})
    runtime_cache = runtime.get("raw_cache", {})
    module_runtime_cache = runtime_cache.get("modules", {}).get(module_id, {})

    candidates = [
        payload.get("cache_enabled"),
        payload.get("use_cache"),
        payload_cache.get("enabled") if isinstance(payload_cache, dict) else payload_cache,
        payload_cache.get("use") if isinstance(payload_cache, dict) else None,
        module_runtime_cache.get("enabled") if isinstance(module_runtime_cache, dict) else None,
        module_runtime_cache.get("use") if isinstance(module_runtime_cache, dict) else None,
        runtime_cache.get("enabled") if isinstance(runtime_cache, dict) else runtime_cache,
        runtime_cache.get("use") if isinstance(runtime_cache, dict) else None,
        runtime.get("raw_cache_enabled"),
    ]

    for candidate in candidates:
        parsed = _parse_bool(candidate)
        if parsed is not None:
            return parsed
    return default_enabled
