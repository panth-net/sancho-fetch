from __future__ import annotations

from datetime import datetime
from typing import Any

from sancho.runtime.contracts import ModuleContext


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    title = payload.get("title", "Sancho Fetch Dashboard")
    metrics = payload.get("metrics", {})

    lines = [f"# {title}", "", f"Generated: {datetime.utcnow().isoformat()}Z", ""]
    for key, value in metrics.items():
        lines.append(f"- **{key}**: {value}")

    report_path = context.data_outputs_path / "dashboard_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"report_path": str(report_path)}
