from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.runtime

from sancho.cli import main
from sancho.runtime.contracts import ModuleContext
from sancho.runtime.data_store import load_raw, resolve_staleness_seconds, save_raw
from sancho.runtime.executor import run_module


def test_save_raw_writes_source_shaped_record(tmp_path: Path) -> None:
    import yaml

    record = save_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw={"rows": [{"value": 1}]},
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at="2026-03-30T12:00:00+00:00",
    )

    record_dir = record.record_dir
    assert record_dir is not None
    # Layout: <root>/<module>/<family>/<request_key>/<timestamp>/{data,request,provenance,content,README}
    assert record_dir.parent.parent.parent.parent == tmp_path
    assert (record_dir / "data.json").exists()
    assert (record_dir / "request.yml").exists()
    assert (record_dir / "provenance.yml").exists()
    assert (record_dir / "content.sha256").exists()
    assert (record_dir / "README.md").exists()

    stored_raw = json.loads((record_dir / "data.json").read_text(encoding="utf-8"))
    assert stored_raw == {"rows": [{"value": 1}]}

    provenance = yaml.safe_load((record_dir / "provenance.yml").read_text(encoding="utf-8"))
    assert provenance["source_url"] == "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL"
    assert provenance["fetched_at"] == "2026-03-30T12:00:00+00:00"
    assert provenance["module_id"] == "fetch.world_bank"
    assert provenance["family"] == "v2.data.country_indicator"
    assert provenance["content_sha256"]

    request = yaml.safe_load((record_dir / "request.yml").read_text(encoding="utf-8"))
    assert request["params"] == {"format": "json"}

    hash_text = (record_dir / "content.sha256").read_text(encoding="utf-8")
    assert hash_text.startswith("sha256:")
    assert "data.json" in hash_text

    # Catalog index file appended.
    index_jsonl = tmp_path / "_catalog" / "cache-index.jsonl"
    assert index_jsonl.exists()
    line = index_jsonl.read_text(encoding="utf-8").splitlines()[0]
    event = json.loads(line)
    assert event["event"] == "save"
    assert event["module_id"] == "fetch.world_bank"


def _build_context(tmp_path: Path, *, runtime: dict[str, Any] | None = None) -> ModuleContext:
    return ModuleContext(
        workspace_root=tmp_path,
        data_raw_path=tmp_path / "raw",
        data_refined_path=tmp_path / "refined",
        data_outputs_path=tmp_path / "outputs",
        env={},
        runtime=runtime or {},
    )


def test_save_raw_and_load_raw_support_context_signature(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    context = _build_context(tmp_path)
    payload = {"rows": [{"value": 99}]}
    meta = {
        "params": {"format": "json"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        "fetched_at": fetched_at.isoformat(),
        "request_id": "abc-123",
    }

    saved = save_raw(context, "fetch.world_bank", "v2.data.country_indicator", payload, meta)
    assert saved == payload

    loaded = load_raw(
        context,
        "fetch.world_bank",
        "v2.data.country_indicator",
        max_age_seconds=120,
        now=fetched_at + timedelta(seconds=60),
    )
    assert loaded == payload

    record = load_raw(
        data_raw_path=context.data_raw_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        max_age_seconds=120,
        now=fetched_at + timedelta(seconds=60),
    )
    assert record is not None
    assert record.metadata["request_id"] == "abc-123"


def test_load_raw_filters_by_freshness_and_request_identity(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    save_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw={"rows": [{"value": 1}]},
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at=fetched_at.isoformat(),
    )

    fresh = load_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        max_age_seconds=120,
        now=fetched_at + timedelta(seconds=90),
    )
    assert fresh is not None
    assert fresh.raw == {"rows": [{"value": 1}]}

    stale = load_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        max_age_seconds=30,
        now=fetched_at + timedelta(seconds=90),
    )
    assert stale is None

    wrong_request = load_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        params={"format": "xml"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        max_age_seconds=120,
        now=fetched_at + timedelta(seconds=90),
    )
    assert wrong_request is None


def test_load_raw_does_not_use_cache_without_explicit_staleness(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    save_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw={"rows": [{"value": 1}]},
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at=fetched_at.isoformat(),
    )

    cached = load_raw(
        data_raw_path=tmp_path,
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        max_age_seconds=None,
        now=fetched_at + timedelta(seconds=1),
    )
    assert cached is None


def test_resolve_staleness_seconds_requires_explicit_setting() -> None:
    assert resolve_staleness_seconds(payload={}, runtime={}, module_id="fetch.world_bank") is None
    assert (
        resolve_staleness_seconds(
            payload={"cache": {"max_age_seconds": "45"}},
            runtime={},
            module_id="fetch.world_bank",
        )
        == 45
    )


@pytest.mark.parametrize(
    ("module_id", "input_payload", "family_or_dataset_id", "source_url", "cache_params", "cached_raw"),
    [
        (
            "fetch.world_bank",
            {
                "base": "v2",
                "method": "GET",
                "path": "/country/all/indicator/SP.POP.TOTL",
                "params": {"format": "json", "per_page": 1000},
                "cache_max_age_seconds": 3600,
            },
            "v2.data.country_indicator",
            "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
            {"format": "json", "per_page": 1000},
            [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 42}]],
        ),
        (
            "fetch.nyc_open_data",
            {
                "base": "nyc_v2",
                "method": "GET",
                "path": "/resource/erm2-nwe9.json",
                "params": {"$limit": 1},
                "body": {},
                "cache_max_age_seconds": 3600,
            },
            "soda.v2.resource",
            "https://data.cityofnewyork.us/resource/erm2-nwe9.json",
            {"query": {"$limit": 1}, "body": {}},
            [{"unique_key": "1", "borough": "MANHATTAN"}],
        ),
    ],
)
def test_module_runtime_uses_fresh_raw_cache_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module_id: str,
    input_payload: dict[str, Any],
    family_or_dataset_id: str,
    source_url: str,
    cache_params: dict[str, Any],
    cached_raw: Any,
) -> None:
    def fail_http(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Network should not be called when raw cache is fresh")

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fail_http)

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", module_id, "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    fetched_at = datetime.now(timezone.utc).isoformat()
    save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id=module_id,
        family_or_dataset_id=family_or_dataset_id,
        raw=cached_raw,
        params=cache_params,
        source_url=source_url,
        fetched_at=fetched_at,
    )

    result = run_module(workspace, module_id=module_id, input_payload=input_payload)
    assert result.status == "ok"
    assert result.output["raw"] == cached_raw
    assert result.output["retrieved_at"] == fetched_at


@pytest.mark.parametrize(
    ("module_id", "input_payload", "family_or_dataset_id", "source_url", "cache_params", "cached_raw", "network_raw"),
    [
        (
            "fetch.world_bank",
            {
                "base": "v2",
                "method": "GET",
                "path": "/country/all/indicator/SP.POP.TOTL",
                "params": {"format": "json", "per_page": 1000},
            },
            "v2.data.country_indicator",
            "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
            {"format": "json", "per_page": 1000},
            [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 42}]],
            [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 84}]],
        ),
        (
            "fetch.nyc_open_data",
            {
                "base": "nyc_v2",
                "method": "GET",
                "path": "/resource/erm2-nwe9.json",
                "params": {"$limit": 1},
                "body": {},
            },
            "soda.v2.resource",
            "https://data.cityofnewyork.us/resource/erm2-nwe9.json",
            {"query": {"$limit": 1}, "body": {}},
            [{"unique_key": "1", "borough": "MANHATTAN"}],
            [{"unique_key": "2", "borough": "BROOKLYN"}],
        ),
    ],
)
def test_module_runtime_skips_raw_cache_without_explicit_staleness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module_id: str,
    input_payload: dict[str, Any],
    family_or_dataset_id: str,
    source_url: str,
    cache_params: dict[str, Any],
    cached_raw: Any,
    network_raw: Any,
) -> None:
    calls = {"count": 0}

    def fake_http(self: Any, method: str, url: str, params=None, headers=None, json_body=None) -> Any:
        calls["count"] += 1
        return network_raw

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_http)

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", module_id, "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id=module_id,
        family_or_dataset_id=family_or_dataset_id,
        raw=cached_raw,
        params=cache_params,
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

    result = run_module(workspace, module_id=module_id, input_payload=input_payload)
    assert result.status == "ok"
    assert calls["count"] == 1
    assert result.output["raw"] == network_raw
