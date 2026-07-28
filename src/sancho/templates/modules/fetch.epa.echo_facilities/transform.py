from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    # EPA ECHO REST returns {"Results": {"Facilities": [...], "ClusterOutput": {...}, ...}}
    rows = extract_rows(
        raw,
        preferred_keys=("Results.Facilities", "Results.ClusterOutput.ClusterData"),
    )
    return {
        "dataset_ref": "usgov_epa",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
