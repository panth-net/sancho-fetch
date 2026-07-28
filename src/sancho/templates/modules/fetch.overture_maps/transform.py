from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(
    *,
    source_url: str,
    raw: Any,
    theme: str,
    release: str,
    bbox: list[float],
) -> dict[str, Any]:
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    row_count = raw.get("row_count", len(rows)) if isinstance(raw, dict) else 0
    error = raw.get("error") if isinstance(raw, dict) else None

    result: dict[str, Any] = {
        "dataset_ref": "intl_overture_maps",
        "source_url": source_url,
        "theme": theme,
        "release": release,
        "bbox": bbox,
        "rows": rows,
        "row_count": row_count,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        result["error"] = error
        result["instructions"] = raw.get("instructions", "")
    return result
