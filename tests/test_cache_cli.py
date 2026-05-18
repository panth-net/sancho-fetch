from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.templates.runtime.data_store import save_raw


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


_DEFAULT_RAW = {"rows": [{"value": 42}]}


def _seed_cache(workspace: Path, params: dict, raw=_DEFAULT_RAW) -> None:
    save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw=raw,
        params=params,
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at="2026-03-30T12:00:00+00:00",
    )


def test_cache_list_returns_empty_when_no_cache(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main(["cache", "list", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"records": [], "count": 0}


def test_cache_list_reports_seeded_record(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_cache(workspace, {"format": "json"})
    capsys.readouterr()
    rc = main(["cache", "list", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    record = payload["records"][0]
    assert record["module_id"] == "fetch.world_bank"
    assert record["family"] == "v2.data.country_indicator"
    assert record["data_bytes"] > 0
    assert record["content_sha256"]


def test_cache_status_reports_missing_when_record_absent(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    request_file = tmp_path / "request.yml"
    request_file.write_text(yaml.safe_dump({
        "module_id": "fetch.world_bank",
        "family": "v2.data.country_indicator",
        "params": {"format": "xml"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
    }), encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "cache", "status",
        "--module", "fetch.world_bank",
        "--request-file", str(request_file),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "missing"
    assert payload["missing_units"] == 1
    assert payload["cached_units"] == 0


def test_cache_status_reports_cached_for_matching_request(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_cache(workspace, {"format": "json"})
    request_file = tmp_path / "request.yml"
    request_file.write_text(yaml.safe_dump({
        "module_id": "fetch.world_bank",
        "family": "v2.data.country_indicator",
        "params": {"format": "json"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
    }), encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "cache", "status",
        "--module", "fetch.world_bank",
        "--request-file", str(request_file),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "cached"
    assert payload["cached_units"] == 1
    assert payload["history_count"] >= 1


def test_cache_status_accepts_inline_request_json(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_cache(workspace, {"format": "json"})
    request = {
        "module_id": "fetch.world_bank",
        "family": "v2.data.country_indicator",
        "params": {"format": "json"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
    }
    capsys.readouterr()
    rc = main([
        "cache", "status",
        "--module", "fetch.world_bank",
        "--request-json", json.dumps(request),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "cached"
    assert payload["cached_units"] == 1


def test_cache_status_rejects_request_file_and_request_json_together(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    _init_workspace(tmp_path)
    request_file = tmp_path / "request.yml"
    request_file.write_text("family: x\n", encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "cache", "status",
        "--module", "fetch.world_bank",
        "--request-file", str(request_file),
        "--request-json", "{}",
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["error_code"] == "unhandled_error"
    assert "Use only one" in payload["error_message"]


def test_cache_status_reports_empty_result_for_empty_payload(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_cache(workspace, {"format": "json"}, raw=[])
    request_file = tmp_path / "request.yml"
    request_file.write_text(yaml.safe_dump({
        "module_id": "fetch.world_bank",
        "family": "v2.data.country_indicator",
        "params": {"format": "json"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
    }), encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "cache", "status",
        "--module", "fetch.world_bank",
        "--request-file", str(request_file),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "empty_result"
    assert payload["empty_units"] == 1


def test_cache_status_reports_corrupt_when_data_tampered(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_cache(workspace, {"format": "json"})
    # Find the record and corrupt its data.json
    fetched_data = workspace / "fetched-data"
    data_files = list(fetched_data.rglob("data.json"))
    assert data_files
    data_files[0].write_text('{"rows": [{"value": 999}]}', encoding="utf-8")  # different content, hash mismatch

    request_file = tmp_path / "request.yml"
    request_file.write_text(yaml.safe_dump({
        "module_id": "fetch.world_bank",
        "family": "v2.data.country_indicator",
        "params": {"format": "json"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
    }), encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "cache", "status",
        "--module", "fetch.world_bank",
        "--request-file", str(request_file),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "corrupt"
    assert payload["corrupt_units"] == 1


def test_cache_show_locates_record_by_id(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_cache(workspace, {"format": "json"})
    capsys.readouterr()
    rc = main(["cache", "list", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    record_id = payload["records"][0]["record_id"]
    capsys.readouterr()
    rc = main(["cache", "show", record_id, "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["provenance"]["module_id"] == "fetch.world_bank"
    assert detail["request"]["params"] == {"format": "json"}
