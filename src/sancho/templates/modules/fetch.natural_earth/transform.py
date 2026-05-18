from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(*, level: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    return {
        "dataset_ref": "natural_earth",
        "level": level,
        "params": params,
        "rows": rows,
        "feature_count": len(rows),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
