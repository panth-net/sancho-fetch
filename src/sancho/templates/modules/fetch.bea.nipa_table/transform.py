from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _extract_bea_rows(raw: Any) -> list[dict[str, Any]]:
    """BEA wraps data at raw.BEAAPI.Results.Data[]."""
    if not isinstance(raw, dict):
        return []
    results = raw.get("BEAAPI", {}).get("Results")
    # Results can be a dict with Data list, or a list if multi-dataset
    if isinstance(results, dict):
        data = results.get("Data", [])
        if isinstance(data, list):
            return data
    elif isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            data = first.get("Data", [])
            if isinstance(data, list):
                return data
    return []


def build_output(*, table_name: str, year: str, frequency: str, raw: Any) -> dict[str, Any]:
    rows = _extract_bea_rows(raw)
    return {
        "dataset_ref": "usgov_bea",
        "table_name": table_name,
        "year": year,
        "frequency": frequency,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
