from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sancho.catalog_tiers import large_catalog_path
from sancho.constants import MODULE_TEMPLATES_ROOT


def slugify_module_id(module_id: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in module_id)


def provider_to_module_id(provider: str) -> str:
    cleaned = provider.strip()
    if cleaned.startswith("fetch."):
        return cleaned
    return f"fetch.{cleaned}"


def module_dir_for_workspace(workspace_root: Path, module_id: str) -> Path:
    return workspace_root / "source" / "fetch" / slugify_module_id(module_id)


def module_dir_for_template(module_id: str) -> Path:
    return MODULE_TEMPLATES_ROOT / module_id


def module_catalog_json_file(module_dir: Path) -> Path:
    return large_catalog_path(module_dir)


def _resolve_catalog_file(
    module_dir: Path, cache_root: Path | None, module_id: str | None
) -> Path | None:
    from sancho.catalog_cache import resolve_catalog_artifact

    return resolve_catalog_artifact(
        module_dir, cache_root, "catalog.json", module_id=module_id
    )


def _load_provider_catalog_from_json(
    module_dir: Path,
    *,
    cache_root: Path | None = None,
    module_id: str | None = None,
) -> dict[str, Any] | None:
    catalog_file = _resolve_catalog_file(module_dir, cache_root, module_id)
    if catalog_file is None:
        return None
    payload = json.loads(catalog_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    provider_obj = payload.get("provider")
    families_obj = payload.get("families", [])
    if not isinstance(provider_obj, str):
        return None
    families = [item for item in families_obj if isinstance(item, dict)] if isinstance(families_obj, list) else []
    return {
        "provider": provider_obj,
        "families": families,
        "catalog": payload,
    }


def load_provider_catalog(
    module_dir: Path,
    *,
    cache_root: Path | None = None,
    module_id: str | None = None,
) -> dict[str, Any]:
    json_catalog = _load_provider_catalog_from_json(
        module_dir, cache_root=cache_root, module_id=module_id
    )
    if json_catalog is not None:
        return json_catalog
    catalog_file = module_catalog_json_file(module_dir)
    raise FileNotFoundError(
        f"Provider catalog.json not found at {catalog_file} "
        f"(and not in catalog cache). Run 'sancho add {module_id or module_dir.name}' "
        f"or 'sancho module catalog refresh {module_id or module_dir.name}'."
    )


def resolve_provider_catalog(workspace_root: Path, provider: str) -> tuple[str, Path, dict[str, Any]]:
    from sancho.catalog_cache import resolve_cache_dir
    from sancho.config import load_workspace_config

    module_id = provider_to_module_id(provider)
    installed_dir = module_dir_for_workspace(workspace_root, module_id)
    if not installed_dir.exists():
        raise KeyError(
            f"Provider module '{module_id}' is not installed in this workspace. "
            f"Run 'sancho add {module_id}' first."
        )
    cache_root = resolve_cache_dir(load_workspace_config(workspace_root))
    catalog = load_provider_catalog(
        installed_dir, cache_root=cache_root, module_id=module_id
    )
    return module_id, installed_dir, catalog
