from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModuleContext:
    workspace_root: Path
    data_raw_path: Path
    data_refined_path: Path
    data_outputs_path: Path
    env: dict[str, str]
    runtime: dict[str, Any]
    catalog_cache_dir: Path | None = None
    storage: dict[str, Any] | None = None
    # Canonical Sancho Fetch v2 paths. These default to the legacy
    # data_raw_path / data_refined_path / data_outputs_path values so
    # existing modules using the old names keep working unchanged.
    fetched_data_path: Path | None = None
    analysis_data_path: Path | None = None
    logs_path: Path | None = None
    update_backups_path: Path | None = None

    def __post_init__(self) -> None:
        if self.fetched_data_path is None:
            self.fetched_data_path = self.data_raw_path
        if self.analysis_data_path is None:
            self.analysis_data_path = self.data_refined_path
        if self.logs_path is None:
            self.logs_path = self.workspace_root / "logs"
        if self.update_backups_path is None:
            self.update_backups_path = self.workspace_root / "update-backups"


@dataclass
class ModuleRunResult:
    module_id: str
    status: str
    output: Any
