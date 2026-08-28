from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sancho.runtime.contracts import ModuleContext


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    title = payload.get("title", "Sancho Fetch Dashboard")
    metrics = payload.get("metrics", {})

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [f"# {title}", "", f"Generated: {generated_at}", ""]
    for key, value in metrics.items():
        lines.append(f"- **{key}**: {value}")

    report_path = context.data_outputs_path / "dashboard_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"report_path": str(report_path)}
