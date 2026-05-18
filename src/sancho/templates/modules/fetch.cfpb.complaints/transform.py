from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.transform_rows import extract_rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    # CFPB returns Elasticsearch envelope: hits.hits[*]._source
    rows = extract_rows(raw, preferred_keys=("hits.hits",), unwrap_source=True)
    return {
        "dataset_ref": "usgov_cfpb",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
