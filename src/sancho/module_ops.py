from __future__ import annotations

from pathlib import Path
from typing import Any

from sancho.catalog_cache import resolve_cache_dir
from sancho.config import load_workspace_config
from sancho.datasource_standard import STANDARD_DOC_PATH, parse_standard_check_ids, run_standard_checks, summarize_standard_results
from sancho.modules import (
    discover_module_map,
    discover_modules,
    normalize_rel,
    regenerate_lock,
    validate_manifest_payload,
)
from sancho.catalog_tiers import LARGE_TIER, catalog_tier_from_manifest
from sancho.provider_discovery import has_discovery_file, is_provider_module_id, run_module_discovery


def list_module_ids(workspace_root: Path) -> list[str]:
    ids = {module.id for module in discover_modules(workspace_root)}
    return sorted(ids)


def validate_all_manifests(workspace_root: Path) -> list[str]:
    errors: list[str] = []
    for module in discover_modules(workspace_root):
        try:
            validate_manifest_payload(module.manifest)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"{module.workspace_rel}: {exc}")
    return errors


def refresh_module_catalog(workspace_root: Path, module_id: str, *, offline: bool = False) -> dict[str, Any]:
    source = discover_module_map(workspace_root, zone="source")
    location = source.get(module_id)
    if location is None:
        raise KeyError(f"Module '{module_id}' is not installed in source/")
    if location.type != "fetch" or not is_provider_module_id(module_id):
        raise ValueError(f"Module '{module_id}' is not a provider module (expected fetch.*)")
    if not has_discovery_file(location.module_dir):
        raise ValueError(f"Module '{module_id}' does not define discovery.py and cannot refresh catalog.")
    if catalog_tier_from_manifest(location.manifest) == LARGE_TIER and offline:
        raise ValueError(f"{module_id} requires live catalog generation; --offline is not supported.")

    result = run_module_discovery(location.module_dir, offline=offline)
    required_ids = parse_standard_check_ids(STANDARD_DOC_PATH)
    cache_root = resolve_cache_dir(load_workspace_config(workspace_root))
    checks = run_standard_checks(
        location.module_dir,
        required_ids=required_ids,
        cache_root=cache_root,
        module_id=module_id,
    )
    ok, passed, total = summarize_standard_results(checks)
    if not ok:
        failed = [item for item in checks if not bool(item.get("passed"))]
        failed_text = "; ".join(f"{item['id']}: {item['detail']}" for item in failed)
        raise RuntimeError(
            f"Provider module '{module_id}' failed implementation standard checks ({passed}/{total}): {failed_text}"
        )
    regenerate_lock(workspace_root)
    return result


def audit_provider_modules(workspace_root: Path) -> list[dict[str, Any]]:
    required_ids = parse_standard_check_ids(STANDARD_DOC_PATH)
    cache_root = resolve_cache_dir(load_workspace_config(workspace_root))
    provider_modules = [
        module
        for module in discover_modules(workspace_root, zone="source")
        if module.type == "fetch"
        and is_provider_module_id(module.id)
        and has_discovery_file(module.module_dir)
    ]
    reports: list[dict[str, Any]] = []
    for module in provider_modules:
        checks = run_standard_checks(
            module.module_dir,
            required_ids=required_ids,
            cache_root=cache_root,
            module_id=module.id,
        )
        ok, passed, total = summarize_standard_results(checks)
        reports.append(
            {
                "module_id": module.id,
                "module_dir": normalize_rel(module.module_dir.relative_to(workspace_root)),
                "ok": ok,
                "passed": passed,
                "total": total,
                "checks": checks,
            }
        )
    return reports
