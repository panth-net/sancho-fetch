from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(*, series_id: str, raw: Any) -> dict[str, Any]:
    observations = raw.get("observations", []) if isinstance(raw, dict) else []
    return {
        "dataset_ref": "usgov_fred",
        "series_id": series_id,
        "observations": observations,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
