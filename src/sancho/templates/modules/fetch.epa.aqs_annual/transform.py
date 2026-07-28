
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("results", "data", "Data", "items", "records", "observations", "hits"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    rows = _extract_rows(raw)
    return {
        "dataset_ref": "usgov_epa_aqs",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
