from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(
    *, source_url: str, raw: Any, params: dict[str, Any],
) -> dict[str, Any]:
    rows: list = raw.get("rows", []) if isinstance(raw, dict) else []
    # If no resource URLs extracted, fall back to the dataflow metadata as a single row
    # (the endpoint returns dataflow metadata -- this gives callers *something* meaningful)
    if not rows and isinstance(raw, dict):
        metadata = raw.get("metadata")
        if isinstance(metadata, dict) and metadata:
            rows = [metadata]
    return {
        "dataset_ref": "intl_oecd_dac_crs",
        "source_url": source_url,
        "params": params,
        "rows": rows,
        "row_count": len(rows),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
