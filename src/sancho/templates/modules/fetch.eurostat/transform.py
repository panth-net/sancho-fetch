from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _dimension_tables(raw: dict[str, Any]) -> list[tuple[str, list[str], dict[str, str]]]:
    """Per dimension: (dimension id, codes ordered by index, code -> label)."""
    tables: list[tuple[str, list[str], dict[str, str]]] = []
    for dim_id in raw.get("id") or []:
        dim = (raw.get("dimension") or {}).get(dim_id) or {}
        category = dim.get("category") or {}
        index = category.get("index") or {}
        if isinstance(index, list):
            ordered = [str(code) for code in index]
        else:
            ordered = sorted(index, key=index.get)
        labels = {str(k): str(v) for k, v in (category.get("label") or {}).items()}
        tables.append((str(dim_id), ordered, labels))
    return tables


def jsonstat_rows(raw: Any) -> list[dict[str, Any]]:
    """Flatten a JSON-stat 2.0 response into one row per observation.

    The API returns values keyed by a linear index over the dimension sizes;
    each index is unraveled back to one code (and label) per dimension.
    """
    if not isinstance(raw, dict) or not raw.get("id"):
        return []
    tables = _dimension_tables(raw)
    sizes = [len(codes) for _, codes, _ in tables]
    if not sizes or any(size == 0 for size in sizes):
        return []
    values = raw.get("value")
    if isinstance(values, dict):
        items = [(int(k), v) for k, v in values.items()]
    elif isinstance(values, list):
        items = list(enumerate(values))
    else:
        return []
    rows: list[dict[str, Any]] = []
    for linear_index, value in items:
        remaining = linear_index
        coords: list[int] = []
        for size in reversed(sizes):
            coords.append(remaining % size)
            remaining //= size
        coords.reverse()
        row: dict[str, Any] = {}
        for (dim_id, codes, labels), position in zip(tables, coords):
            code = codes[position]
            row[dim_id] = code
            label = labels.get(code)
            if label and label != code:
                row[f"{dim_id}_label"] = label
        row["value"] = value
        rows.append(row)
    return rows


def build_output(*, source_url: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("rows"), list):
        rows = raw["rows"]
    else:
        rows = jsonstat_rows(raw)
    return {
        "dataset_ref": str(params.get("dataset") or "eurostat"),
        "source_url": source_url,
        "params": params,
        "rows": rows,
        "row_count": len(rows),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
