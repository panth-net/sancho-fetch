from __future__ import annotations

import re
from typing import Any

from sancho.runtime.contracts import ModuleContext


def _to_snake(value: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", value)
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", cleaned)
    return cleaned.strip("_").lower()


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records", [])
    normalized = []
    for row in records:
        if not isinstance(row, dict):
            continue
        normalized.append({_to_snake(str(k)): v for k, v in row.items()})

    return {"records": normalized, "count": len(normalized)}
