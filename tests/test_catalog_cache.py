from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from sancho import catalog_cache
from sancho.catalog_cache import (
    CatalogDownloadError,
    cached_module_dir,
    default_global_cache_dir,
    download_prebuilt_catalog,
    prune_raw_snapshots,
    resolve_cache_dir,
    resolve_catalog_artifact,
    resolve_mirror_url,
)
from sancho.config import _merged_workspace_config, load_workspace_config
from sancho.provider_kits import load_provider_catalog


class _FakeResp:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeSession:
    def __init__(self, map_: dict[str, _FakeResp]) -> None:
        self._map = map_
        self.calls: list[str] = []

    def get(self, url: str, timeout: float = 20.0) -> _FakeResp:
        self.calls.append(url)
        if url in self._map:
            return self._map[url]
        return _FakeResp(404)


def test_default_cache_dir_under_home() -> None:
    cache = default_global_cache_dir()
    assert cache.name == "catalogs"
    assert cache.parent.name == ".sancho"


def test_resolve_cache_dir_honors_config(tmp_path: Path) -> None:
    cfg = {"catalog": {"cache_dir": str(tmp_path / "mycache")}}
    resolved = resolve_cache_dir(cfg)
    assert resolved == (tmp_path / "mycache").resolve()


def test_resolve_cache_dir_defaults_when_empty() -> None:
    assert resolve_cache_dir({"catalog": {"cache_dir": ""}}) == default_global_cache_dir()
    assert resolve_cache_dir(None) == default_global_cache_dir()
    assert resolve_cache_dir({}) == default_global_cache_dir()


def test_resolve_mirror_url_trims_and_none_for_empty() -> None:
    assert resolve_mirror_url({"catalog": {"mirror_url": "  https://example.com/cats/  "}}) == "https://example.com/cats/"
    assert resolve_mirror_url({"catalog": {"mirror_url": ""}}) is None
    assert resolve_mirror_url({}) is None
    assert resolve_mirror_url(None) is None


def test_resolve_catalog_artifact_prefers_module_dir(tmp_path: Path) -> None:
    module_dir = tmp_path / "fetch_bls"
    module_dir.mkdir()
    (module_dir / "catalog.json").write_text("{}", encoding="utf-8")
    cache = tmp_path / "cache"
    cached = cache / "fetch_bls"
    cached.mkdir(parents=True)
    (cached / "catalog.json").write_text("{}", encoding="utf-8")
    result = resolve_catalog_artifact(module_dir, cache, "catalog.json", module_id="fetch.bls")
    assert result == module_dir / "catalog.json"


def test_resolve_catalog_artifact_falls_back_to_cache(tmp_path: Path) -> None:
    module_dir = tmp_path / "fetch.bls"
    module_dir.mkdir()
    cache = tmp_path / "cache"
    cached_dir = cached_module_dir(cache, "fetch.bls")
    cached_dir.mkdir(parents=True)
    cached_file = cached_dir / "catalog.json"
    cached_file.write_text("{}", encoding="utf-8")
    result = resolve_catalog_artifact(module_dir, cache, "catalog.json", module_id="fetch.bls")
    assert result == cached_file


def test_resolve_catalog_artifact_returns_none_when_missing(tmp_path: Path) -> None:
    module_dir = tmp_path / "missing"
    module_dir.mkdir()
    cache = tmp_path / "cache"
    assert resolve_catalog_artifact(module_dir, cache, "catalog.json", module_id="fetch.x") is None
    assert resolve_catalog_artifact(module_dir, None, "catalog.json", module_id="fetch.x") is None


def test_resolve_catalog_artifact_rejects_unknown_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_catalog_artifact(tmp_path, None, "not_an_artifact.json")


def test_load_provider_catalog_uses_cache(tmp_path: Path) -> None:
    module_dir = tmp_path / "fetch.world_bank"
    module_dir.mkdir()
    cache = tmp_path / "cache"
    cached_dir = cached_module_dir(cache, "fetch.world_bank")
    cached_dir.mkdir(parents=True)
    (cached_dir / "catalog.json").write_text(
        json.dumps({"provider": "fetch.world_bank", "families": [{"id": "f1"}]}),
        encoding="utf-8",
    )
    result = load_provider_catalog(module_dir, cache_root=cache, module_id="fetch.world_bank")
    assert result["provider"] == "fetch.world_bank"
    assert result["families"] == [{"id": "f1"}]


def test_load_provider_catalog_raises_when_missing_everywhere(tmp_path: Path) -> None:
    module_dir = tmp_path / "fetch.x"
    module_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_provider_catalog(module_dir, cache_root=tmp_path / "cache", module_id="fetch.x")


def test_merged_workspace_config_fills_missing_sections() -> None:
    legacy = {"version": 1, "mode": "operator", "runtime": {"http": {"timeout_seconds": 20}}}
    merged = _merged_workspace_config(legacy)
    assert merged["catalog"] == {"mirror_url": "", "cache_dir": ""}
    assert merged["storage"] == {"retention": {}}
    assert merged["runtime"]["http"]["timeout_seconds"] == 20


def test_load_workspace_config_merges_legacy(tmp_path: Path) -> None:
    (tmp_path / "sancho.yaml").write_text("version: 1\nmode: coder\n", encoding="utf-8")
    cfg = load_workspace_config(tmp_path)
    assert "catalog" in cfg and cfg["catalog"]["mirror_url"] == ""
    assert "storage" in cfg and cfg["storage"]["retention"] == {}


def test_download_prebuilt_catalog_empty_mirror(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = download_prebuilt_catalog(
        "fetch.bls", mirror_url="", cache_root=tmp_path / "cache"
    )
    assert result == []
    err = capsys.readouterr().err
    assert "mirror URL not configured" in err


def test_download_prebuilt_catalog_writes_files(tmp_path: Path) -> None:
    cat_body = json.dumps({"provider": "fetch.bls", "families": []}).encode("utf-8")
    meta_body = json.dumps({"generated_at": "2026-01-01"}).encode("utf-8")
    session = _FakeSession(
        {
            "https://mirror/fetch_bls/catalog.json": _FakeResp(200, content=cat_body),
            "https://mirror/fetch_bls/catalog.meta.json": _FakeResp(200, content=meta_body),
            "https://mirror/fetch_bls/schema.sample.json": _FakeResp(404),
        }
    )
    written = download_prebuilt_catalog(
        "fetch.bls",
        mirror_url="https://mirror/",
        cache_root=tmp_path / "cache",
        session=session,
    )
    names = {p.name for p in written}
    assert names == {"catalog.json", "catalog.meta.json"}
    assert len(session.calls) == 3


def test_download_prebuilt_catalog_raises_on_non_404_error(tmp_path: Path) -> None:
    session = _FakeSession(
        {
            "https://mirror/fetch_bls/catalog.json": _FakeResp(500, text="boom"),
        }
    )
    with pytest.raises(CatalogDownloadError):
        download_prebuilt_catalog(
            "fetch.bls",
            mirror_url="https://mirror",
            cache_root=tmp_path / "cache",
            session=session,
        )


def test_prune_raw_snapshots_respects_keep_and_age(tmp_path: Path) -> None:
    # Phase 3 layout: snapshots are timestamped directories.
    snapdir = tmp_path / "raw"
    snapdir.mkdir()
    now = datetime(2026, 4, 16, tzinfo=timezone.utc)

    def make(name: str, days_old: int) -> Path:
        d = snapdir / name
        d.mkdir()
        (d / "data.json").write_text("{}", encoding="utf-8")
        mtime = (now - timedelta(days=days_old)).timestamp()
        os.utime(d, (mtime, mtime))
        return d

    recent1 = make("20260416T000000Z", 0)
    recent2 = make("20260415T000000Z", 1)
    middle = make("20260316T000000Z", 31)
    old = make("20260101T000000Z", 105)

    deleted = prune_raw_snapshots(snapdir, keep_last_n=2, max_age_days=90, now=now)

    assert {p.name for p in deleted} == {old.name}
    assert recent1.exists()
    assert recent2.exists()
    assert middle.exists()
    assert not old.exists()


def test_prune_raw_snapshots_noop_when_both_disabled(tmp_path: Path) -> None:
    snapdir = tmp_path / "raw"
    snapdir.mkdir()
    (snapdir / "a").mkdir()
    assert prune_raw_snapshots(snapdir, keep_last_n=0, max_age_days=0) == []
    assert (snapdir / "a").exists()


def test_prune_keep_zero_max_age_deletes_all_older(tmp_path: Path) -> None:
    snapdir = tmp_path / "raw"
    snapdir.mkdir()
    now = datetime(2026, 4, 16, tzinfo=timezone.utc)
    young = snapdir / "young"
    young.mkdir()
    old = snapdir / "old"
    old.mkdir()
    young_mtime = (now - timedelta(days=1)).timestamp()
    old_mtime = (now - timedelta(days=10)).timestamp()
    os.utime(young, (young_mtime, young_mtime))
    os.utime(old, (old_mtime, old_mtime))

    deleted = prune_raw_snapshots(snapdir, keep_last_n=0, max_age_days=5, now=now)
    assert {p.name for p in deleted} == {"old"}
    assert young.exists()
    assert not old.exists()


def _make_context(tmp_path: Path, storage: dict[str, Any] | None = None) -> Any:
    from sancho.runtime.contracts import ModuleContext

    return ModuleContext(
        workspace_root=tmp_path,
        data_raw_path=tmp_path / "raw",
        data_refined_path=tmp_path / "refined",
        data_outputs_path=tmp_path / "outputs",
        env={},
        runtime={},
        catalog_cache_dir=None,
        storage=storage,
    )


def _request_key_dir(tmp_path: Path, module_id: str, family: str, params: dict, source_url: str) -> Path:
    from sancho.templates.runtime.data_store import _compute_request_key, _request_key_dir as _rk_dir
    return _rk_dir(tmp_path / "raw", module_id, family, _compute_request_key(params, source_url))


def test_save_raw_without_retention_keeps_all_snapshots(tmp_path: Path) -> None:
    from sancho.runtime.data_store import save_raw

    context = _make_context(tmp_path, storage=None)
    fetched_at = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)
    same_params: dict = {"k": "v"}
    for index in range(4):
        moment = fetched_at + timedelta(seconds=index)
        save_raw(
            context,
            "fetch.dummy",
            "family_a",
            {"n": index},
            {"params": same_params, "source_url": "https://example.com", "fetched_at": moment.isoformat()},
        )
    rk_dir = _request_key_dir(tmp_path, "fetch.dummy", "family_a", same_params, "https://example.com")
    timestamps = [p for p in rk_dir.iterdir() if p.is_dir()]
    assert len(timestamps) == 4


def test_save_raw_with_retention_prunes_old_snapshots(tmp_path: Path) -> None:
    from sancho.runtime.data_store import save_raw

    context = _make_context(tmp_path, storage={"retention": {"keep_last_n": 2, "max_age_days": 1}})
    fetched_at = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)
    same_params: dict = {"k": "v"}
    rk_dir = _request_key_dir(tmp_path, "fetch.dummy", "family_a", same_params, "https://example.com")
    rk_dir.mkdir(parents=True)

    # Seed 2 old snapshot directories beyond retention window.
    for index, days_ago in enumerate([10, 5]):
        d = rk_dir / f"old_{index}"
        d.mkdir()
        (d / "data.json").write_text("{}", encoding="utf-8")
        mtime = (fetched_at - timedelta(days=days_ago)).timestamp()
        os.utime(d, (mtime, mtime))

    # Write a fresh snapshot via save_raw — should trigger pruning.
    save_raw(
        context,
        "fetch.dummy",
        "family_a",
        {"n": 1},
        {"params": same_params, "source_url": "https://example.com", "fetched_at": fetched_at.isoformat()},
    )

    remaining = sorted(p.name for p in rk_dir.iterdir() if p.is_dir())
    # keep_last_n=2 AND age=1d: top 2 by mtime stay regardless of age.
    # With 3 dirs (2 old + 1 new), top 2 keep {new, old_1 (5 days)}, old_0 (10 days) gets deleted.
    assert len(remaining) == 2
    assert not (rk_dir / "old_0").exists()
