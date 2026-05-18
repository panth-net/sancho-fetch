from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

CATALOG_ARTIFACTS = ("catalog.json", "catalog.meta.json", "schema.sample.json")


def _slug(module_id: str) -> str:
    from sancho.provider_kits import slugify_module_id

    return slugify_module_id(module_id)


class CatalogDownloadError(Exception):
    pass


def default_global_cache_dir() -> Path:
    return (Path.home() / ".sancho" / "catalogs").resolve()


def resolve_cache_dir(config: dict[str, Any] | None) -> Path:
    raw = ""
    if isinstance(config, dict):
        catalog_cfg = config.get("catalog") or {}
        raw = str(catalog_cfg.get("cache_dir", "") or "").strip()
    if not raw:
        return default_global_cache_dir()
    return Path(raw).expanduser().resolve()


def resolve_mirror_url(config: dict[str, Any] | None) -> str | None:
    if not isinstance(config, dict):
        return None
    catalog_cfg = config.get("catalog") or {}
    raw = str(catalog_cfg.get("mirror_url", "") or "").strip()
    return raw or None


def cached_module_dir(cache_root: Path, module_id: str) -> Path:
    return cache_root / _slug(module_id)


def resolve_catalog_artifact(
    module_dir: Path,
    cache_root: Path | None,
    artifact: str,
    *,
    module_id: str | None = None,
) -> Path | None:
    if artifact not in CATALOG_ARTIFACTS:
        raise ValueError(f"Unknown catalog artifact: {artifact}")
    local = module_dir / artifact
    if local.exists():
        return local
    if cache_root is None:
        return None
    if module_id is None:
        module_id = module_dir.name
    cached = cached_module_dir(cache_root, module_id) / artifact
    if cached.exists():
        return cached
    return None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def download_prebuilt_catalog(
    module_id: str,
    *,
    mirror_url: str | None,
    cache_root: Path,
    timeout: float = 20.0,
    session: requests.Session | None = None,
) -> list[Path]:
    if not mirror_url:
        print(
            f"[catalog_cache] mirror URL not configured; skipping prebuilt download for {module_id}",
            file=sys.stderr,
        )
        return []
    base = mirror_url.rstrip("/")
    slug = _slug(module_id)
    target_dir = cached_module_dir(cache_root, module_id)
    http = session or requests
    written: list[Path] = []
    for artifact in CATALOG_ARTIFACTS:
        url = f"{base}/{slug}/{artifact}"
        try:
            resp = http.get(url, timeout=timeout)
        except requests.RequestException as exc:
            raise CatalogDownloadError(f"Network error fetching {url}: {exc}") from exc
        if resp.status_code == 404:
            continue
        if resp.status_code >= 400:
            raise CatalogDownloadError(
                f"HTTP {resp.status_code} fetching {url}: {resp.text[:200]}"
            )
        dest = target_dir / artifact
        _atomic_write_bytes(dest, resp.content)
        written.append(dest)
    return written


def _paired_meta(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".meta.json")


def prune_raw_snapshots(
    snapshot_dir: Path,
    *,
    keep_last_n: int,
    max_age_days: int,
    now: datetime | None = None,
) -> list[Path]:
    """Prune cache snapshots in ``snapshot_dir``.

    Snapshots are timestamped subdirectories under a request_key directory
    (Phase 3 layout). Each directory is one cache record. The function keeps
    the newest ``keep_last_n`` directories and deletes anything older than
    ``max_age_days`` after that.
    """
    if keep_last_n <= 0 and max_age_days <= 0:
        return []
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        return []
    snapshots = [p for p in snapshot_dir.iterdir() if p.is_dir()]
    if not snapshots:
        return []
    snapshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    ref_now = now or datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)
    cutoff = ref_now - timedelta(days=max_age_days) if max_age_days > 0 else None

    keep_count = max(keep_last_n, 0)
    deleted: list[Path] = []
    for index, snapshot in enumerate(snapshots):
        if index < keep_count:
            continue
        if cutoff is not None:
            mtime = datetime.fromtimestamp(snapshot.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                continue
        try:
            shutil.rmtree(snapshot)
        except OSError:
            continue
        deleted.append(snapshot)
    return deleted
