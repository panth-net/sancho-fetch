from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from sancho.catalog_tiers import VALID_FETCH_CATALOG_TIERS
from sancho.config import load_lock_config, load_modules_config, write_lock_config, write_modules_config
from sancho.constants import MODULE_TEMPLATES_ROOT, SUPPORTED_MODULE_TYPES
from sancho.module_install_status import ModuleInstallResult, catalog_state_for_module
from sancho.module_packs import MODULE_PACKS
from sancho.provider_discovery import has_discovery_file, is_provider_module_id
from sancho.provider_install_discovery import (
    fetch_prebuilt_or_warn,
    run_provider_discovery_with_fallback,
)
from sancho.utils import file_sha256, read_yaml, utc_now_iso, write_yaml

REQUIRED_MANIFEST_FIELDS = {"id", "version", "type", "entrypoint", "managed_paths"}
@dataclass
class ModuleLocation:
    id: str
    version: str
    type: str
    entrypoint: str
    zone: str
    module_dir: Path
    workspace_rel: str
    manifest: dict[str, Any]

@dataclass
class TemplateModule:
    id: str
    version: str
    type: str
    template_dir: Path
    manifest: dict[str, Any]

    def target_dir(self, workspace_root: Path) -> Path:
        return workspace_root / "source" / self.type / slugify_module_id(self.id)


def slugify_module_id(module_id: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in module_id)
def normalize_rel(path: Path) -> str:
    return path.as_posix()


def validate_manifest_payload(payload: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(payload.keys()))
    if missing:
        raise ValueError(f"module.yaml missing required fields: {', '.join(missing)}")
    if payload["type"] not in SUPPORTED_MODULE_TYPES:
        raise ValueError(f"Unsupported module type: {payload['type']}")
    if payload["type"] == "fetch":
        catalog_tier_obj = payload.get("catalog_tier")
        catalog_tier = str(catalog_tier_obj).strip().lower() if isinstance(catalog_tier_obj, str) else ""
        if catalog_tier not in VALID_FETCH_CATALOG_TIERS:
            known = ", ".join(sorted(VALID_FETCH_CATALOG_TIERS))
            raise ValueError(f"fetch module.yaml requires catalog_tier ({known})")
    try:
        Version(str(payload["version"]))
    except InvalidVersion as exc:
        raise ValueError(f"Invalid semantic version '{payload['version']}'") from exc


def load_template_registry() -> dict[str, TemplateModule]:
    registry: dict[str, TemplateModule] = {}
    if not MODULE_TEMPLATES_ROOT.exists():
        return registry
    for template_dir in MODULE_TEMPLATES_ROOT.iterdir():
        if not template_dir.is_dir():
            continue
        manifest_path = template_dir / "module.yaml"
        if not manifest_path.exists():
            continue
        payload = read_yaml(manifest_path, default={})
        validate_manifest_payload(payload)
        module = TemplateModule(
            id=payload["id"],
            version=str(payload["version"]),
            type=payload["type"],
            template_dir=template_dir,
            manifest=payload,
        )
        registry[module.id] = module
    return registry


def _copy_template(template_dir: Path, target_dir: Path, overwrite: bool) -> list[Path]:
    copied: list[Path] = []
    for src in template_dir.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(template_dir)
        if "__pycache__" in rel.parts or src.suffix == ".pyc":
            continue
        dst = target_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not overwrite:
            continue
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def _module_paths_from_manifest(module_dir: Path, manifest: dict[str, Any], workspace_root: Path) -> list[str]:
    managed = manifest.get("managed_paths") or []
    if not managed:
        managed = [normalize_rel(path.relative_to(module_dir)) for path in module_dir.rglob("*") if path.is_file()]
    result: list[str] = []
    for item in managed:
        rel_path = (module_dir / item).resolve().relative_to(workspace_root.resolve())
        result.append(normalize_rel(rel_path))
    return sorted(set(result))


def discover_modules(workspace_root: Path, zone: str | None = None) -> list[ModuleLocation]:
    zones = [zone] if zone else ["source", "custom"]
    items: list[ModuleLocation] = []
    for current_zone in zones:
        if current_zone not in {"source", "custom"}:
            continue
        zone_root = workspace_root / current_zone
        if not zone_root.exists():
            continue
        for module_type in SUPPORTED_MODULE_TYPES:
            type_root = zone_root / module_type
            if not type_root.exists():
                continue
            for manifest_path in type_root.rglob("module.yaml"):
                module_dir = manifest_path.parent
                payload = read_yaml(manifest_path, default={})
                validate_manifest_payload(payload)
                items.append(
                    ModuleLocation(
                        id=payload["id"],
                        version=str(payload["version"]),
                        type=payload["type"],
                        entrypoint=payload["entrypoint"],
                        zone=current_zone,
                        module_dir=module_dir,
                        workspace_rel=normalize_rel(module_dir.relative_to(workspace_root)),
                        manifest=payload,
                    )
                )
    return sorted(items, key=lambda item: (item.zone, item.type, item.id))


def discover_module_map(workspace_root: Path, zone: str | None = None) -> dict[str, ModuleLocation]:
    return {module.id: module for module in discover_modules(workspace_root, zone=zone)}


def install_module(
    workspace_root: Path,
    module_id: str,
    channel: str = "stable",
    *,
    discover: bool = False,
) -> Path:
    registry = load_template_registry()
    if module_id not in registry:
        known = ", ".join(sorted(registry.keys()))
        raise KeyError(f"Unknown module '{module_id}'. Known modules: {known}")

    template = registry[module_id]
    target_dir = template.target_dir(workspace_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    _copy_template(template.template_dir, target_dir, overwrite=True)
    if template.type == "fetch" and is_provider_module_id(module_id) and has_discovery_file(target_dir):
        if discover:
            run_provider_discovery_with_fallback(module_id, target_dir)
        else:
            fetch_prebuilt_or_warn(workspace_root, module_id, target_dir)

    modules_cfg = load_modules_config(workspace_root)
    modules = modules_cfg.setdefault("modules", {})
    modules[module_id] = {
        "enabled": True,
        "channel": channel,
        "type": template.type,
        "source": {
            "kind": "builtin",
            "template": module_id,
        },
        "config": {},
    }
    write_modules_config(workspace_root, modules_cfg)
    regenerate_lock(workspace_root)
    return target_dir


def install_target(
    workspace_root: Path,
    target_id: str,
    channel: str = "stable",
    *,
    discover: bool = False,
) -> list[ModuleInstallResult]:
    registry = load_template_registry()
    target_ids = MODULE_PACKS.get(target_id, [target_id])

    results: list[ModuleInstallResult] = []
    for module_id in target_ids:
        if module_id not in registry:
            known_modules = sorted(registry.keys())
            known_targets = sorted(set(known_modules + list(MODULE_PACKS.keys())))
            known = ", ".join(known_targets)
            raise KeyError(f"Unknown module or pack '{module_id}'. Known targets: {known}")
        installed_path = install_module(
            workspace_root, module_id=module_id, channel=channel, discover=discover
        )
        state, detail = catalog_state_for_module(
            workspace_root, module_id, installed_path, registry[module_id].manifest
        )
        results.append(
            ModuleInstallResult(
                module_id=module_id,
                install_path=installed_path,
                catalog_state=state,
                detail=detail,
            )
        )
    return results


def _compare_versions(installed: str, available: str) -> int:
    try:
        installed_version = Version(installed)
        available_version = Version(available)
    except InvalidVersion:
        return 0
    if available_version > installed_version:
        return 1
    if available_version == installed_version:
        return 0
    return -1


def preview_updates(workspace_root: Path, module_id: str | None = None) -> list[dict[str, Any]]:
    registry = load_template_registry()
    installed = discover_module_map(workspace_root, zone="source")
    lock = load_lock_config(workspace_root)

    target_ids = [module_id] if module_id else sorted(installed.keys())
    actions: list[dict[str, Any]] = []
    for current_id in target_ids:
        location = installed.get(current_id)
        if not location:
            continue
        template = registry.get(current_id)
        lock_entry = lock.get("modules", {}).get(current_id, {})
        action = None
        details: dict[str, Any] = {
            "module_id": current_id,
            "installed_version": location.version,
        }

        if template:
            details["available_version"] = template.version
            version_cmp = _compare_versions(location.version, template.version)
            if version_cmp > 0:
                action = "upgrade_available"

        if not action and lock_entry:
            checksums = lock_entry.get("checksums", {})
            for rel_path, expected in checksums.items():
                candidate = workspace_root / rel_path
                if not candidate.exists():
                    action = "reconcile_managed_drift"
                    details["drift_path"] = rel_path
                    break
                if file_sha256(candidate) != expected:
                    action = "reconcile_managed_drift"
                    details["drift_path"] = rel_path
                    break

        if action:
            details["action"] = action
            actions.append(details)

    return actions


def apply_updates(workspace_root: Path, actions: list[dict[str, Any]]) -> list[str]:
    registry = load_template_registry()
    changed: set[str] = set()
    installed = discover_module_map(workspace_root, zone="source")

    for action in actions:
        module_id = action["module_id"]
        template = registry.get(module_id)
        location = installed.get(module_id)
        if not template or not location:
            continue
        for path in _copy_template(template.template_dir, location.module_dir, overwrite=True):
            changed.add(normalize_rel(path.relative_to(workspace_root)))
        if template.type == "fetch" and is_provider_module_id(module_id) and has_discovery_file(location.module_dir):
            run_provider_discovery_with_fallback(module_id, location.module_dir)

    regenerate_lock(workspace_root)
    changed.add("modules.lock.yaml")
    return sorted(changed)


def regenerate_lock(workspace_root: Path) -> dict[str, Any]:
    modules_cfg = load_modules_config(workspace_root)
    previous_lock = load_lock_config(workspace_root)
    installed = discover_modules(workspace_root, zone="source")

    modules: dict[str, Any] = {}
    for module in installed:
        managed_paths = _module_paths_from_manifest(module.module_dir, module.manifest, workspace_root)
        checksums = {
            rel_path: file_sha256(workspace_root / rel_path)
            for rel_path in managed_paths
            if (workspace_root / rel_path).exists()
        }
        previous_installed_at = previous_lock.get("modules", {}).get(module.id, {}).get("installed_at")
        desired_cfg = modules_cfg.get("modules", {}).get(module.id, {})
        source_payload = desired_cfg.get("source") or {"kind": "local", "template": module.id}
        modules[module.id] = {
            "version": module.version,
            "source": source_payload,
            "resolved_revision": file_sha256(module.module_dir / "module.yaml"),
            "installed_at": previous_installed_at or utc_now_iso(),
            "checksums": checksums,
            "managed_paths": managed_paths,
        }

    lock_payload = {
        "version": 1,
        "generated_at": utc_now_iso(),
        "modules": modules,
    }
    write_lock_config(workspace_root, lock_payload)
    return lock_payload


def resolve_module_for_execution(workspace_root: Path, module_id: str) -> ModuleLocation:
    custom = discover_module_map(workspace_root, zone="custom")
    if module_id in custom:
        return custom[module_id]
    source = discover_module_map(workspace_root, zone="source")
    if module_id in source:
        return source[module_id]
    raise KeyError(f"Module '{module_id}' not found in custom or source.")
