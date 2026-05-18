from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, domain: str, dataset_id: str, raw: Any) -> dict[str, Any]:
    rows = extract_rows(raw)
    return {
        "dataset_ref": "socrata_generic",
        "domain": domain,
        "dataset_id": dataset_id,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
