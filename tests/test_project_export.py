from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.project_export import LARGE_BUNDLE_BYTES, PROJECT_FOLDER, export_record_to_project
from sancho.templates.runtime.data_store import save_raw


def test_project_bundle_folder_name_is_filesystem_safe() -> None:
    assert PROJECT_FOLDER == "sancho-fetched-data"
    assert " " not in PROJECT_FOLDER


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def _seed_record(workspace: Path, raw=None) -> Path:
    record = save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw=raw if raw is not None else [{"country": "US", "value": 42}, {"country": "CA", "value": 36}],
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at="2026-04-01T12:00:00+00:00",
    )
    assert record.record_dir is not None
    return record.record_dir


def test_export_copies_small_record_as_bundle(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    record_dir = _seed_record(workspace)
    project = tmp_path / "Some Project"

    result = export_record_to_project(
        record_dir=record_dir,
        project_root=project,
        workspace_root=workspace,
    )

    assert result.mode == "copy"
    assert (result.bundle_dir / "README.md").exists()
    assert (result.bundle_dir / "manifest.yml").exists()
    assert (result.bundle_dir / "provenance.yml").exists()
    assert (result.bundle_dir / "source-cache-links.yml").exists()
    assert (result.bundle_dir / "data.json").exists()
    # Tabular payload should also produce data.csv.
    assert (result.bundle_dir / "data.csv").exists()
    manifest = yaml.safe_load((result.bundle_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["mode"] == "copy"
    assert manifest["record_count"] == 1
    assert manifest["records"][0]["module_id"] == "fetch.world_bank"


def test_export_creates_pointer_bundle_for_large_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _init_workspace(tmp_path)
    record_dir = _seed_record(workspace)
    # Force the size check to think this is "large".
    monkeypatch.setattr("sancho.project_export.LARGE_BUNDLE_BYTES", 1)
    project = tmp_path / "Other Project"

    result = export_record_to_project(
        record_dir=record_dir,
        project_root=project,
        workspace_root=workspace,
    )

    assert result.mode == "pointer"
    # Pointer mode: NO full data.json copy, just a small sample.
    assert not (result.bundle_dir / "data.json").exists()
    assert (result.bundle_dir / "data.sample.json").exists()
    links = yaml.safe_load((result.bundle_dir / "source-cache-links.yml").read_text(encoding="utf-8"))
    assert links["records"][0]["data_file"].endswith("data.json")


def test_export_does_not_mutate_canonical_record(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    record_dir = _seed_record(workspace)
    before = (record_dir / "data.json").read_text(encoding="utf-8")

    project = tmp_path / "Untouched Project"
    export_record_to_project(record_dir=record_dir, project_root=project, workspace_root=workspace)

    after = (record_dir / "data.json").read_text(encoding="utf-8")
    assert before == after


def test_cli_export_to_project_finds_record_by_request_key(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    record_dir = _seed_record(workspace)
    # Pull the request_key out of provenance for the CLI to find the record.
    prov = yaml.safe_load((record_dir / "provenance.yml").read_text(encoding="utf-8"))
    request_key = prov["request_key"]
    project = tmp_path / "Project By Key"
    project.mkdir()
    capsys.readouterr()

    rc = main([
        "export-to-project",
        "--cache-record", request_key,
        "--project", str(project),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    bundle = Path(payload["bundle_dir"])
    assert bundle.exists()
    assert bundle.parent.name == PROJECT_FOLDER


def test_cli_export_to_project_fails_when_no_record_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main([
        "export-to-project",
        "--cache-record", "deadbeef0000",
        "--project", str(tmp_path),
        "--workspace", str(tmp_path),
    ])
    assert rc == 1


def test_cli_export_to_project_via_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_record(workspace)  # canonical record exists

    # Run the module to produce a run_id in logs.
    monkeypatch.setattr(
        "sancho.runtime.http.HttpClient.request_json",
        lambda self, method, url, params=None, headers=None, json_body=None:
            [{"page": 1}, [{"country": "US", "value": 99}]],
    )
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({
        "base": "v2", "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
        "params": {"format": "json"},
    }), encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "run", "fetch.world_bank",
        "--workspace", str(tmp_path),
        "--input", str(input_file),
    ])
    assert rc == 0
    # The run also auto-bundles because CWD is outside the workspace's parent.
    # That's fine — the explicit export below targets a different project folder.
    capsys.readouterr()

    # Pull a run_id from logs.
    runs_path = workspace / "logs" / "runs.jsonl"
    run_id = None
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event_type") == "run_finished":
            run_id = event["run_id"]
    assert run_id is not None

    project = tmp_path / "Project Via Run"
    project.mkdir()
    rc = main([
        "export-to-project",
        "--run-id", run_id,
        "--project", str(project),
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    bundle = Path(payload["bundle_dir"])
    assert bundle.exists()
