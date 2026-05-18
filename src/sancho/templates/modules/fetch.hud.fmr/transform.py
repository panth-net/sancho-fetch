from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_output(*, url: str, raw: Any) -> dict[str, Any]:
    return {
        "dataset_ref": "usgov_hud",
        "url": url,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
