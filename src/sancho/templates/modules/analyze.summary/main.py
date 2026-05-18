from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sancho.runtime.contracts import ModuleContext


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records", [])
    metrics = {
        "record_count": len(records),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    output_path = context.data_outputs_path / "analysis_summary.json"
    output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return {"output_path": str(output_path), "metrics": metrics}
