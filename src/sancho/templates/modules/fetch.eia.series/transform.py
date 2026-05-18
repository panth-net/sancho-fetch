from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    # EIA v2 returns {"response": {"data": [...]}}
    if isinstance(raw, dict) and isinstance(raw.get("response"), dict):
        rows = extract_rows(raw["response"])
    else:
        rows = extract_rows(raw)
    return {
        "dataset_ref": "usgov_eia",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
