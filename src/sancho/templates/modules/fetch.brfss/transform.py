from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(
    *,
    source_url: str,
    raw: Any,
    year: int | None,
    file_kind: str | None,
) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    rows = data.get("rows", [])
    files = data.get("files", [])
    return {
        "dataset_ref": "usgov_cdc_brfss",
        "source_url": source_url,
        "year": year,
        "file_kind": file_kind,
        "files": files,
        "rows": rows,
        "row_count": len(rows),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
