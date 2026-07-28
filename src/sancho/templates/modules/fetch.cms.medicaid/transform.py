from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    rows = extract_rows(raw, preferred_keys=("dataset", "results", "data", "items"))
    # Special case: data.medicaid.gov's /data.json returns "dataset" as a dict
    # of {"0": {...}, "1": {...}} rather than a list. Unpack values.
    if not rows and isinstance(raw, dict):
        ds = raw.get("dataset")
        if isinstance(ds, dict) and ds:
            rows = list(ds.values())
    return {
        "dataset_ref": "usgov_medicaid",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
