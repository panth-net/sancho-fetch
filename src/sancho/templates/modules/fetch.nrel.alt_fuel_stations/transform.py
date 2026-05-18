from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    # NREL returns {"total_results": N, "fuel_stations": [...]}
    rows = extract_rows(raw, preferred_keys=("fuel_stations",))
    return {
        "dataset_ref": "usgov_nrel",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
