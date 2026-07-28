from __future__ import annotations

import sys
from pathlib import Path

from sancho.catalog_cache import (
    CatalogDownloadError,
    download_prebuilt_catalog,
    resolve_cache_dir,
    resolve_mirror_url,
)
from sancho.config import load_workspace_config
from sancho.datasource_standard import STANDARD_DOC_PATH, parse_standard_check_ids, run_standard_checks, summarize_standard_results
from sancho.provider_discovery import run_module_discovery


def enforce_provider_standard(
    module_id: str,
    module_dir: Path,
    *,
    cache_root: Path | None = None,
) -> None:
    required_ids = parse_standard_check_ids(STANDARD_DOC_PATH)
    checks = run_standard_checks(
        module_dir,
        required_ids=required_ids,
        cache_root=cache_root,
        module_id=module_id,
    )
    ok, passed, total = summarize_standard_results(checks)
    if ok:
        return
    failed = [item for item in checks if not bool(item.get("passed"))]
    failed_text = "; ".join(f"{item['id']}: {item['detail']}" for item in failed)
    raise RuntimeError(
        f"Provider module '{module_id}' failed implementation standard checks ({passed}/{total}): {failed_text}"
    )


def _format_exception(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def run_provider_discovery_with_fallback(
    module_id: str,
    module_dir: Path,
    *,
    cache_root: Path | None = None,
) -> None:
    try:
        run_module_discovery(module_dir, offline=False)
    except Exception as live_exc:
        try:
            enforce_provider_standard(module_id, module_dir, cache_root=cache_root)
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Provider module '{module_id}' live discovery failed and seeded catalog fallback is invalid.\n"
                f"Live discovery error: {_format_exception(live_exc)}\n"
                f"Seeded artifact validation error: {_format_exception(fallback_exc)}\n"
                f"Remediation: run `sancho module catalog refresh {module_id}` when network/provider is healthy."
            ) from live_exc
        print(
            f"WARNING: Provider discovery fallback for '{module_id}' - "
            f"live discovery failed ({_format_exception(live_exc)}); using seeded catalog artifacts.",
            file=sys.stderr,
        )
        return
    enforce_provider_standard(module_id, module_dir, cache_root=cache_root)


def fetch_prebuilt_or_warn(workspace_root: Path, module_id: str, module_dir: Path) -> None:
    seeded_catalog = (module_dir / "catalog.json").exists()
    config = load_workspace_config(workspace_root)
    mirror_url = resolve_mirror_url(config)
    cache_root = resolve_cache_dir(config)
    if not mirror_url:
        if seeded_catalog:
            return
        print(
            f"[sancho add] No seeded catalog for '{module_id}' and no mirror configured. "
            f"Run 'sancho add {module_id} --discover' or 'sancho module catalog refresh {module_id}' "
            f"to generate one.",
            file=sys.stderr,
        )
        return
    try:
        written = download_prebuilt_catalog(
            module_id, mirror_url=mirror_url, cache_root=cache_root
        )
    except CatalogDownloadError as exc:
        if seeded_catalog:
            return
        print(
            f"[sancho add] Prebuilt catalog download failed for '{module_id}': {exc}. "
            f"Run 'sancho module catalog refresh {module_id}' when network/provider is healthy.",
            file=sys.stderr,
        )
        return
    if not written and not seeded_catalog:
        print(
            f"[sancho add] No prebuilt catalog on mirror for '{module_id}'. "
            f"Use 'sancho add {module_id} --discover' or 'sancho module catalog refresh {module_id}' "
            f"to generate one.",
            file=sys.stderr,
        )
