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
        # Reuse a cached record for an identical request within this window so
        # repeated/identical fetches don't re-hit the provider API (saves rate
        # limit / quota and is faster). Slow-moving official statistics make a
        # 24h default safe; force fresh with `cache:{max_age_seconds:0}`,
        # `cache:{enabled:false}`, or `refresh:true` in the request.
        "raw_cache": {
            "enabled": True,
            "max_age_seconds": 86400,
        },
    },
    "catalog": {
        "mirror_url": "",
        "cache_dir": "",
    },
    "storage": {
        "retention": {},
    },
    "exports": {
        "public_working_copy_enabled": True,
        "public_folder_name": "sancho-downloads",
        "show_only_primary_path_by_default": True,
        "prefer_csv_when_lossless": True,
        "keep_original_alongside_conversion": True,
        "unzip_archives": True,
        "large_file_warn_bytes": 100 * 1024 * 1024,  # 100 MB
        "max_label_chars": 48,
        "filename_hash_chars": 8,
    },
}


_CATALOG_DEFAULTS = {"mirror_url": "", "cache_dir": ""}
_STORAGE_DEFAULTS = {"retention": {}}
_EXPORTS_DEFAULTS = {
    "public_working_copy_enabled": True,
    "public_folder_name": "sancho-downloads",
    "show_only_primary_path_by_default": True,
    "prefer_csv_when_lossless": True,
    "keep_original_alongside_conversion": True,
    "unzip_archives": True,
    "large_file_warn_bytes": 100 * 1024 * 1024,
    "max_label_chars": 48,
    "filename_hash_chars": 8,
}


_RUNTIME_DEFAULTS = {
    "raw_cache": {"enabled": True, "max_age_seconds": 86400},
}


def _merged_workspace_config(raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(raw)
    # Backfill runtime defaults so workspaces created before a default existed
    # (e.g. raw_cache) still pick it up; an explicit value in sancho.yaml wins.
    runtime = dict(merged.get("runtime") or {})
    for key, default in _RUNTIME_DEFAULTS.items():
        runtime.setdefault(key, default)
    merged["runtime"] = runtime
    catalog = dict(merged.get("catalog") or {})
    for key, default in _CATALOG_DEFAULTS.items():
        catalog.setdefault(key, default)
    merged["catalog"] = catalog
    storage = dict(merged.get("storage") or {})
    for key, default in _STORAGE_DEFAULTS.items():
        storage.setdefault(key, default)
    merged["storage"] = storage
    exports = dict(merged.get("exports") or {})
    for key, default in _EXPORTS_DEFAULTS.items():
        exports.setdefault(key, default)
    merged["exports"] = exports
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
