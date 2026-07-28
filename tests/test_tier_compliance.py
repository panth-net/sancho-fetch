from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from sancho.catalog_tiers import LARGE_TIER, catalog_tier_from_manifest, large_catalog_meta_path, large_catalog_path, small_schema_sample_path
from sancho.constants import MODULE_TEMPLATES_ROOT


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(payload, dict):
        return payload
    return {}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def _iter_fetch_module_dirs() -> list[Path]:
    dirs: list[Path] = []
    if not MODULE_TEMPLATES_ROOT.exists():
        return dirs
    for module_dir in MODULE_TEMPLATES_ROOT.iterdir():
        if not module_dir.is_dir():
            continue
        manifest_path = module_dir / "module.yaml"
        if not manifest_path.exists():
            continue
        manifest = _load_yaml(manifest_path)
        if str(manifest.get("type", "")).strip() != "fetch":
            continue
        dirs.append(module_dir)
    return sorted(dirs)


def _assert_large_tier_contract(module_dir: Path) -> None:
    module_id = module_dir.name

    catalog_path = large_catalog_path(module_dir)
    meta_path = large_catalog_meta_path(module_dir)
    assert catalog_path.exists(), f"{module_id}: missing catalog.json"
    assert meta_path.exists(), f"{module_id}: missing catalog.meta.json"

    catalog = _load_json(catalog_path)
    meta = _load_json(meta_path)

    for key in ("provider", "families", "generated_at"):
        assert key in catalog, f"{module_id}: catalog.json missing key '{key}'"
    for key in ("provider", "stats", "discovery"):
        assert key in meta, f"{module_id}: catalog.meta.json missing key '{key}'"

    assert isinstance(catalog.get("families"), list), f"{module_id}: catalog.json 'families' must be a list"
    assert isinstance(meta.get("stats"), dict), f"{module_id}: catalog.meta.json 'stats' must be an object"
    assert isinstance(meta.get("discovery"), dict), f"{module_id}: catalog.meta.json 'discovery' must be an object"


def _assert_small_tier_contract(module_dir: Path) -> None:
    module_id = module_dir.name

    schema_path = small_schema_sample_path(module_dir)
    assert schema_path.exists(), f"{module_id}: missing schema.sample.json"
    schema = _load_json(schema_path)

    columns_obj = schema.get("columns")
    sample_row_obj = schema.get("sample_row")

    assert isinstance(columns_obj, list), f"{module_id}: schema.sample.json 'columns' must be a list"
    assert columns_obj, f"{module_id}: schema.sample.json 'columns' must not be empty"
    assert isinstance(sample_row_obj, dict), f"{module_id}: schema.sample.json 'sample_row' must be an object"
    assert sample_row_obj, f"{module_id}: schema.sample.json 'sample_row' must not be empty"

    column_names: list[str] = []
    for column in columns_obj:
        assert isinstance(column, dict), f"{module_id}: each schema column must be an object"
        for key in ("name", "type", "sample"):
            assert key in column, f"{module_id}: schema column missing '{key}'"
        name_obj = column.get("name")
        assert isinstance(name_obj, str) and name_obj.strip(), f"{module_id}: schema column name must be a non-empty string"
        column_names.append(name_obj)

    assert sorted(column_names) == sorted(sample_row_obj.keys()), (
        f"{module_id}: schema.sample.json column names must match sample_row keys"
    )


def test_fetch_module_tier_contracts() -> None:
    fetch_module_dirs = _iter_fetch_module_dirs()
    assert fetch_module_dirs, "No fetch module templates found"

    for module_dir in fetch_module_dirs:
        manifest = _load_yaml(module_dir / "module.yaml")
        tier = catalog_tier_from_manifest(manifest)
        if tier == LARGE_TIER:
            _assert_large_tier_contract(module_dir)
        else:
            _assert_small_tier_contract(module_dir)
