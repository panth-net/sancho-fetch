from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(*, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    return {
        "dataset_ref": "earthengine",
        "dataset_id": params.get("dataset_id", ""),
        "mode": params.get("mode", "raster"),
        "params": params,
        "rows": rows,
        "row_count": len(rows),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
