from __future__ import annotations

from pathlib import Path
from typing import Any


LARGE_TIER = "large"
SMALL_TIER = "small"
VALID_FETCH_CATALOG_TIERS = {LARGE_TIER, SMALL_TIER}


def is_fetch_manifest(manifest: dict[str, Any]) -> bool:
    module_type = str(manifest.get("type", "")).strip()
    return module_type == "fetch"


def catalog_tier_from_manifest(manifest: dict[str, Any]) -> str:
    tier = str(manifest.get("catalog_tier", "")).strip().lower()
    if tier in VALID_FETCH_CATALOG_TIERS:
        return tier
    return SMALL_TIER


def is_large_tier(manifest: dict[str, Any]) -> bool:
    return catalog_tier_from_manifest(manifest) == LARGE_TIER


def large_catalog_path(module_dir: Path) -> Path:
    return module_dir / "catalog.json"


def large_catalog_meta_path(module_dir: Path) -> Path:
    return module_dir / "catalog.meta.json"


def small_schema_sample_path(module_dir: Path) -> Path:
    return module_dir / "schema.sample.json"
