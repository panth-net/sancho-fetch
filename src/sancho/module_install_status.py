from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sancho.catalog_cache import resolve_catalog_artifact


@dataclass(frozen=True)
class ModuleInstallResult:
    module_id: str
    install_path: Path
    catalog_state: str
    detail: str = ""

    def __iter__(self) -> Iterator[object]:
        yield self.module_id
        yield self.install_path


def catalog_state_for_module(
    workspace_root: Path,
    module_id: str,
    module_dir: Path,
    manifest: dict,
) -> tuple[str, str]:
    module_type = str(manifest.get("type", "")).strip()
    if module_type != "fetch":
        return "ready", "non-fetch module"

    tier = str(manifest.get("catalog_tier", "small")).strip().lower() or "small"
    if tier != "large":
        return "ready_without_catalog_but_fetch_still_works", f"catalog_tier={tier}"

    cache_root = None
    try:
        from sancho.catalog_cache import resolve_cache_dir
        from sancho.config import load_workspace_config

        cache_root = resolve_cache_dir(load_workspace_config(workspace_root))
    except Exception:
        cache_root = None

    missing_artifacts = [
        name
        for name in ("catalog.json", "catalog.meta.json")
        if resolve_catalog_artifact(module_dir, cache_root, name, module_id=module_id) is None
    ]
    if missing_artifacts:
        return (
            "not_ready_catalog_missing",
            f"large-tier provider requires {', '.join(missing_artifacts)}; "
            "run with --discover or configure a catalog mirror",
        )
    return "ready", "catalog artifacts available"
