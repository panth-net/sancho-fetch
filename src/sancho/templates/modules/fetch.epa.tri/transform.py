from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("results", "data", "items", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def build_output(
    *, endpoint: str, raw: Any, params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dataset_ref": "usgov_epa_tri",
        "endpoint": endpoint,
        "params": params,
        "rows": _extract_rows(raw),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
