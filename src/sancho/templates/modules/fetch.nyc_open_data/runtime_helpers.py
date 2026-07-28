from __future__ import annotations

import re
from typing import Any


def extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        rows_obj = raw.get("rows")
        if isinstance(rows_obj, list):
            return rows_obj
        for key in ("results", "result", "items", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return [raw]
    if isinstance(raw, list):
        return raw
    return []


def dataset_ref_for_path(path: str) -> str:
    patterns = [
        r"/resource/([A-Za-z0-9]{4}-[A-Za-z0-9]{4})\.",
        r"/api/v3/views/([A-Za-z0-9]{4}-[A-Za-z0-9]{4})/",
        r"/api/views/([A-Za-z0-9]{4}-[A-Za-z0-9]{4})",
        r"/api/views/metadata/v1/([A-Za-z0-9]{4}-[A-Za-z0-9]{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, path)
        if match:
            return f"nyc_open_data_{match.group(1)}"
    return "nyc_open_data_portal"


def resolve_source_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")
