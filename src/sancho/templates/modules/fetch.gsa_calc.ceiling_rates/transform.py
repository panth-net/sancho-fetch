
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # Elasticsearch envelope: hits.hits[*]._source
        hits_outer = raw.get("hits")
        if isinstance(hits_outer, dict):
            hits_inner = hits_outer.get("hits")
            if isinstance(hits_inner, list):
                return [h["_source"] for h in hits_inner if isinstance(h, dict) and "_source" in h]
        for key in ("results", "data", "Data", "items", "records", "observations"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    rows = _extract_rows(raw)
    return {
        "dataset_ref": "usgov_gsa_calc",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
