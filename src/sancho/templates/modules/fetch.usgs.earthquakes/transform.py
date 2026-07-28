from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    # GeoJSON FeatureCollection: {"type":"FeatureCollection","features":[...]}.
    # Single-event lookup (e.g. eventid=...) returns a bare Feature instead.
    if isinstance(raw, dict) and raw.get("type") == "Feature":
        rows = [raw]
    else:
        rows = extract_rows(raw, preferred_keys=("features",))
    return {
        "dataset_ref": "usgov_usgs",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
