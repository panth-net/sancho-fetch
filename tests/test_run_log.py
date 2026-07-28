from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.run_log import (
    ERRORS_DIR,
    ERRORS_LOG,
    LATEST_MD,
    LOGS_DIRNAME,
    RUNS_LOG,
)


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_successful_module_run_writes_run_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _init_workspace(tmp_path)
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json",
                        lambda self, method, url, params=None, headers=None, json_body=None:
                        [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 42}]])
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    rc = main([
        "run", "fetch.world_bank", "--workspace", str(tmp_path),
        "--input", _write_input(tmp_path, {
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
            "params": {"format": "json"},
        }),
    ])
    assert rc == 0

    runs = _read_jsonl(workspace / LOGS_DIRNAME / RUNS_LOG)
    started = [e for e in runs if e["event_type"] == "run_started"]
    finished = [e for e in runs if e["event_type"] == "run_finished"]
    assert len(started) == 1 and len(finished) == 1
    assert finished[0]["status"] in {"success_with_data", "success_empty"}
    assert finished[0]["module_id"] == "fetch.world_bank"
    assert (workspace / LOGS_DIRNAME / LATEST_MD).exists()


def test_failed_module_run_writes_error_log_and_repair_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _init_workspace(tmp_path)
    def boom(self, method, url, params=None, headers=None, json_body=None):
        raise RuntimeError("simulated upstream failure")
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", boom)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    rc = main([
        "run", "fetch.world_bank", "--workspace", str(tmp_path),
        "--input", _write_input(tmp_path, {
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
            "params": {"format": "json"},
        }),
    ])
    assert rc != 0  # CLI surfaces the failure

    errors = _read_jsonl(workspace / LOGS_DIRNAME / ERRORS_LOG)
    assert errors, "errors.jsonl should have at least one entry"
    last = errors[-1]
    assert last["status"] in {"failed", "skipped_needs_key"}
    packet_path = Path(last["repair_packet_path"])
    assert packet_path.exists()
    assert (workspace / LOGS_DIRNAME / ERRORS_DIR).exists()
    text = packet_path.read_text(encoding="utf-8")
    assert "Sancho run error" in text
    assert "fetch.world_bank" in text


def test_logs_never_record_env_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _init_workspace(tmp_path)
    secret_value = "super-secret-key-xyz-12345"
    monkeypatch.setenv("FRED_API_KEY", secret_value)
    monkeypatch.setenv("UNRELATED_SECRET_TOKEN", "also-do-not-log")
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json",
                        lambda self, method, url, params=None, headers=None, json_body=None:
                        [{"page": 1, "pages": 1}, [{"v": 1}]])
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    main([
        "run", "fetch.world_bank", "--workspace", str(tmp_path),
        "--input", _write_input(tmp_path, {
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
        }),
    ])
    log_text = (workspace / LOGS_DIRNAME / RUNS_LOG).read_text(encoding="utf-8")
    assert secret_value not in log_text
    # Only env key names declared by the module should appear.
    assert "FRED_API_KEY" not in log_text
    assert "UNRELATED_SECRET_TOKEN" not in log_text


def test_cli_run_summary_has_primary_path_and_no_raw_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json",
                        lambda self, method, url, params=None, headers=None, json_body=None:
                        [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 42}]])
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    monkeypatch.chdir(tmp_path)  # exports must land in the tmp project
    capsys.readouterr()
    rc = main([
        "run", "fetch.world_bank", "--workspace", str(tmp_path),
        "--input", _write_input(tmp_path, {
            "base": "v2",
            "method": "GET",
            "path": "/country/US/indicator/SP.POP.TOTL",
        }),
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # One contract on every fetch surface: evidence + file path, never the data.
    assert payload["status"] == "ok"
    assert payload["row_count"] == 1
    assert payload["primary_output_path"]
    assert Path(payload["primary_output_path"]).exists()
    assert "output" not in payload


def test_cli_fetch_run_summary_has_no_raw_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json",
                        lambda self, method, url, params=None, headers=None, json_body=None:
                        [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 42}]])
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    rc = main([
        "fetch", "run", "world_bank", "--workspace", str(tmp_path),
        "--path", "/country/US/indicator/SP.POP.TOTL", "--base", "v2",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["row_count"] == 1
    assert payload["primary_output_path"]
    assert "output" not in payload


def test_cli_log_tail_returns_recent_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json",
                        lambda self, method, url, params=None, headers=None, json_body=None:
                        [{"page": 1, "pages": 1}, [{"v": 1}]])
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    main([
        "run", "fetch.world_bank", "--workspace", str(tmp_path),
        "--input", _write_input(tmp_path, {
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
        }),
    ])
    capsys.readouterr()
    rc = main(["log", "tail", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload
    assert any(e.get("event_type") == "run_finished" for e in payload)
    # The tail view hides fields that repeat identically in every event; they
    # stay in runs.jsonl and `sancho log show <run-id>`.
    for event in payload:
        assert "workspace_path" not in event
        assert "current_project_path" not in event
        assert "module_path" not in event
        assert event.get("module_id")


def test_cli_log_path_prints_logs_dir(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main(["log", "path", "--workspace", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith(LOGS_DIRNAME)


def test_public_output_failure_is_logged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sancho.cli_public_export import auto_public_export
    from sancho.templates.runtime.data_store import save_raw

    library_root = tmp_path / "library"
    workspace = _init_workspace(library_root)
    project = tmp_path / "project"
    project.mkdir()
    record = save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id="fetch.world_bank",
        family_or_dataset_id="sample",
        raw=[{"value": 1}],
        params={},
        source_url="https://example.test/data",
    )

    def boom(**kwargs):
        _ = kwargs
        raise RuntimeError("public export failed")

    monkeypatch.setattr("sancho.cli_public_export.export_records_to_public_outputs", boom)
    monkeypatch.chdir(project)
    auto_public_export(workspace, [record.record_dir], module_id="fetch.world_bank", quiet=True)

    runs = _read_jsonl(workspace / LOGS_DIRNAME / RUNS_LOG)
    events = [e for e in runs if e.get("event_type") == "public_output_failed"]
    assert events
    assert events[-1]["detail"]["error_message"] == "public export failed"


def _write_input(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)
