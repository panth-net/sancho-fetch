from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sancho.utils import read_yaml, write_yaml


@dataclass
class WorkspaceConfig:
    version: int
    mode: str
    module_precedence: list[str]
    paths: dict[str, str]
    runtime: dict[str, Any]


DEFAULT_SANCHO_CONFIG: dict[str, Any] = {
    "version": 1,
    "mode": "operator",
    "module_precedence": ["custom", "source"],
    "paths": {
        "source": "source",
        "custom": "custom",
        "playbooks": "playbooks",
        "fetched_data": "fetched-data",
        "analysis_data": "analysis-data",
        "outputs": "outputs",
        "logs": "logs",
        "update_backups": "update-backups",
    },
    "runtime": {
        "http": {
            "timeout_seconds": 20,
            "max_retries": 3,
            "backoff_seconds": 0.4,
            "rate_limit_per_second": 3,
            "cache_ttl_seconds": 600,
        },
        "logging": {"format": "json"},
    },
    "catalog": {
        "mirror_url": "",
        "cache_dir": "",
    },
    "storage": {
        "retention": {},
    },
}


_CATALOG_DEFAULTS = {"mirror_url": "", "cache_dir": ""}
_STORAGE_DEFAULTS = {"retention": {}}


def _merged_workspace_config(raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(raw)
    catalog = dict(merged.get("catalog") or {})
    for key, default in _CATALOG_DEFAULTS.items():
        catalog.setdefault(key, default)
    merged["catalog"] = catalog
    storage = dict(merged.get("storage") or {})
    for key, default in _STORAGE_DEFAULTS.items():
        storage.setdefault(key, default)
    merged["storage"] = storage
    return merged


DEFAULT_MODULES_CONFIG: dict[str, Any] = {
    "version": 1,
    "modules": {},
}


DEFAULT_LOCK_CONFIG: dict[str, Any] = {
    "version": 1,
    "generated_at": None,
    "modules": {},
}


def load_workspace_config(workspace_root: Path) -> dict[str, Any]:
    raw = read_yaml(workspace_root / "sancho.yaml", default=DEFAULT_SANCHO_CONFIG.copy())
    return _merged_workspace_config(raw if isinstance(raw, dict) else DEFAULT_SANCHO_CONFIG.copy())


def write_workspace_config(workspace_root: Path, payload: dict[str, Any]) -> None:
    write_yaml(workspace_root / "sancho.yaml", payload)


def load_modules_config(workspace_root: Path) -> dict[str, Any]:
    return read_yaml(workspace_root / "modules.yaml", default=DEFAULT_MODULES_CONFIG.copy())


def write_modules_config(workspace_root: Path, payload: dict[str, Any]) -> None:
    write_yaml(workspace_root / "modules.yaml", payload)


def load_lock_config(workspace_root: Path) -> dict[str, Any]:
    return read_yaml(workspace_root / "modules.lock.yaml", default=DEFAULT_LOCK_CONFIG.copy())


def write_lock_config(workspace_root: Path, payload: dict[str, Any]) -> None:
    write_yaml(workspace_root / "modules.lock.yaml", payload)
