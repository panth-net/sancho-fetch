from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from sancho.catalog_tiers import LARGE_TIER, SMALL_TIER, catalog_tier_from_manifest, large_catalog_meta_path, large_catalog_path, small_schema_sample_path


STANDARD_DOC_PATH = Path("project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md")


def _resolve_artifact(
    module_dir: Path,
    cache_root: Path | None,
    module_id: str | None,
    artifact: str,
) -> Path | None:
    from sancho.catalog_cache import resolve_catalog_artifact

    return resolve_catalog_artifact(
        module_dir, cache_root, artifact, module_id=module_id
    )
CHECKLIST_ID_RE = re.compile(r"\[STD-(\d{3})\]")
DEFAULT_CHECK_IDS = [
    "STD-001", "STD-002", "STD-003", "STD-004", "STD-005", "STD-006", "STD-007",
]


def parse_standard_check_ids(doc_path: Path) -> list[str]:
    if not doc_path.exists():
        return list(DEFAULT_CHECK_IDS)
    text = doc_path.read_text(encoding="utf-8")
    ids = [f"STD-{match}" for match in CHECKLIST_ID_RE.findall(text)]
    unique = sorted(set(ids))
    if not unique:
        return list(DEFAULT_CHECK_IDS)
    return unique


def _load_manifest(module_dir: Path) -> dict[str, Any]:
    path = module_dir / "module.yaml"
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(payload, dict):
        return payload
    return {}


def _catalog_tier(module_dir: Path) -> str:
    return catalog_tier_from_manifest(_load_manifest(module_dir))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def _load_large_catalog(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> dict[str, Any]:
    path = _resolve_artifact(module_dir, cache_root, module_id, "catalog.json")
    return _load_json(path) if path is not None else {}


def _load_large_meta(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> dict[str, Any]:
    path = _resolve_artifact(module_dir, cache_root, module_id, "catalog.meta.json")
    return _load_json(path) if path is not None else {}


def _load_small_schema(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> dict[str, Any]:
    path = _resolve_artifact(module_dir, cache_root, module_id, "schema.sample.json")
    return _load_json(path) if path is not None else {}


def _check_discovery_py_exists(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    # discovery.py drives catalog.json generation, so it's only required for
    # large-tier modules. Small-tier modules ship a static schema.sample.json
    # and don't need introspection.
    if _catalog_tier(module_dir) != LARGE_TIER:
        return True, "discovery.py not required for small-tier modules"
    path = module_dir / "discovery.py"
    return path.exists(), "discovery.py exists"


def _check_primary_artifact_exists(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    tier = _catalog_tier(module_dir)
    if tier == LARGE_TIER:
        path = _resolve_artifact(module_dir, cache_root, module_id, "catalog.json")
        return path is not None, "catalog.json present"
    path = _resolve_artifact(module_dir, cache_root, module_id, "schema.sample.json")
    return path is not None, "schema.sample.json present"


def _check_secondary_artifact_exists(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    tier = _catalog_tier(module_dir)
    if tier == LARGE_TIER:
        path = _resolve_artifact(module_dir, cache_root, module_id, "catalog.meta.json")
        return path is not None, "catalog.meta.json present"
    return True, "no secondary file required"


def _check_evidence_snapshot(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    tier = _catalog_tier(module_dir)
    if tier == LARGE_TIER:
        meta = _load_large_meta(module_dir, cache_root, module_id)
        discovery = meta.get("discovery")
        if not isinstance(discovery, dict):
            return False, "catalog.meta.json has discovery metadata"
        sources = discovery.get("sources")
        if not isinstance(sources, list) or not sources:
            return False, "catalog.meta.json has discovery source snapshots"
        return True, "catalog.meta.json has discovery source snapshots"

    schema = _load_small_schema(module_dir, cache_root, module_id)
    sample_row = schema.get("sample_row")
    if not isinstance(sample_row, dict) or not sample_row:
        return False, "schema.sample.json has sample_row"
    return True, "schema.sample.json has sample_row"


def _check_query_contract_shape(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    tier = _catalog_tier(module_dir)
    if tier == LARGE_TIER:
        catalog = _load_large_catalog(module_dir, cache_root, module_id)
        families_obj = catalog.get("families")
        if not isinstance(families_obj, list) or not families_obj:
            return False, "catalog.json has families"
        required_keys = {"id", "base_url", "path_templates", "methods", "query_params"}
        for item in families_obj:
            if not isinstance(item, dict):
                return False, "catalog.json families have required fields"
            if not required_keys.issubset(set(item.keys())):
                return False, "catalog.json families have required fields"
        return True, "catalog.json families have required fields"

    schema = _load_small_schema(module_dir, cache_root, module_id)
    columns = schema.get("columns")
    if not isinstance(columns, list) or not columns:
        return False, "schema.sample.json has columns"
    for column in columns:
        if not isinstance(column, dict):
            return False, "schema.sample.json columns include name/type/sample"
        for key in ("name", "type", "sample"):
            if key not in column:
                return False, "schema.sample.json columns include name/type/sample"
    return True, "schema.sample.json columns include name/type/sample"


def _check_consistency(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    tier = _catalog_tier(module_dir)
    if tier == LARGE_TIER:
        catalog = _load_large_catalog(module_dir, cache_root, module_id)
        meta = _load_large_meta(module_dir, cache_root, module_id)
        families_obj = catalog.get("families", [])
        indices_obj = catalog.get("indices", {})
        stats_obj = meta.get("stats", {})

        if not isinstance(families_obj, list):
            return False, "catalog/meta consistency checks"
        if not isinstance(indices_obj, dict):
            return False, "catalog/meta consistency checks"
        if not isinstance(stats_obj, dict):
            return False, "catalog/meta consistency checks"

        family_count = stats_obj.get("family_count")
        if isinstance(family_count, int) and family_count != len(families_obj):
            return False, "catalog/meta consistency checks"

        for key, value in indices_obj.items():
            if not isinstance(value, list):
                continue
            expected = stats_obj.get(f"{key}_count")
            if isinstance(expected, int) and expected != len(value):
                return False, "catalog/meta consistency checks"
        return True, "catalog/meta consistency checks"

    schema = _load_small_schema(module_dir, cache_root, module_id)
    columns_obj = schema.get("columns", [])
    sample_row = schema.get("sample_row", {})
    if not isinstance(columns_obj, list) or not isinstance(sample_row, dict):
        return False, "schema.sample.json columns align with sample_row"
    column_names = []
    for item in columns_obj:
        if not isinstance(item, dict):
            return False, "schema.sample.json columns align with sample_row"
        name_obj = item.get("name")
        if not isinstance(name_obj, str) or not name_obj:
            return False, "schema.sample.json columns align with sample_row"
        column_names.append(name_obj)
    if sorted(column_names) != sorted(sample_row.keys()):
        return False, "schema.sample.json columns align with sample_row"
    return True, "schema.sample.json columns align with sample_row"


def _check_provenance(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> tuple[bool, str]:
    tier = _catalog_tier(module_dir)
    if tier == LARGE_TIER:
        meta = _load_large_meta(module_dir, cache_root, module_id)
        generated_at = meta.get("generated_at")
        if not isinstance(generated_at, str) or not generated_at.strip():
            return False, "catalog.meta.json has provenance fields"
        discovery = meta.get("discovery")
        if not isinstance(discovery, dict):
            return False, "catalog.meta.json has provenance fields"
        sources_obj = discovery.get("sources", [])
        if not isinstance(sources_obj, list):
            return False, "catalog.meta.json has provenance fields"
        for source in sources_obj:
            if not isinstance(source, dict):
                return False, "catalog.meta.json has provenance fields"
            for key in ("url", "status", "fetched_at"):
                value = source.get(key)
                if not isinstance(value, str) or not value.strip():
                    return False, "catalog.meta.json has provenance fields"
        return True, "catalog.meta.json has provenance fields"

    schema = _load_small_schema(module_dir, cache_root, module_id)
    provider_obj = schema.get("provider")
    generated_at = schema.get("generated_at")
    if not isinstance(provider_obj, str) or not provider_obj.strip():
        return False, "schema.sample.json has provider and generated_at"
    if not isinstance(generated_at, str) or not generated_at.strip():
        return False, "schema.sample.json has provider and generated_at"
    return True, "schema.sample.json has provider and generated_at"


CHECKS: dict[str, Callable[[Path, Path | None, str | None], tuple[bool, str]]] = {
    "STD-001": _check_discovery_py_exists,
    "STD-002": _check_primary_artifact_exists,
    "STD-003": _check_secondary_artifact_exists,
    "STD-004": _check_evidence_snapshot,
    "STD-005": _check_query_contract_shape,
    "STD-006": _check_consistency,
    "STD-007": _check_provenance,
}


def run_standard_checks(
    module_dir: Path,
    *,
    required_ids: list[str],
    cache_root: Path | None = None,
    module_id: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for check_id in required_ids:
        fn = CHECKS.get(check_id)
        if fn is None:
            results.append({"id": check_id, "passed": False, "detail": "No checker implemented"})
            continue
        passed, detail = fn(module_dir, cache_root, module_id)
        results.append({"id": check_id, "passed": passed, "detail": detail})
    return results


def summarize_standard_results(results: list[dict[str, Any]]) -> tuple[bool, int, int]:
    total = len(results)
    passed = len([item for item in results if bool(item.get("passed"))])
    return passed == total, passed, total
