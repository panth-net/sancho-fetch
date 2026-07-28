from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(
    *, source_url: str, raw: Any, params: dict[str, Any],
) -> dict[str, Any]:
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    charts = raw.get("charts", []) if isinstance(raw, dict) else []
    return {
        "dataset_ref": "intl_owid_charts",
        "source_url": source_url,
        "params": params,
        "charts": charts,
        "rows": rows,
        "row_count": len(rows),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
