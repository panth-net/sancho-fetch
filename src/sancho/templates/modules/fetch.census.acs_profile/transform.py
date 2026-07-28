from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(*, geography: str, year: str, rows: Any) -> dict[str, Any]:
    return {
        "dataset_ref": "us_census_api",
        "geography": geography,
        "year": year,
        "rows": rows,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
