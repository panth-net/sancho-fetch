from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.templates.runtime.data_store import save_raw
from sancho.runtime import request_state


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def _make_custom_override(workspace: Path, version: str = "9.9.9") -> Path:
    custom = workspace / "custom" / "fetch" / "fetch_world_bank"
    custom.mkdir(parents=True, exist_ok=True)
    (custom / "module.yaml").write_text(
        f"id: fetch.world_bank\nversion: {version}\ntype: fetch\nentrypoint: main.py:run\n"
        "catalog_tier: large\nmanaged_paths:\n  - module.yaml\n",
        encoding="utf-8",
    )
    (custom / "main.py").write_text("def run(context, payload): return {}\n", encoding="utf-8")
    return custom


def test_custom_status_reports_override_and_upstream_newer(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    _make_custom_override(workspace, version="0.0.1")  # very old custom
    capsys.readouterr()
    rc = main(["custom", "status", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    rows = payload["custom_modules"]
    assert any(r["module_id"] == "fetch.world_bank" and r["shadows_source"] for r in rows)
    assert any(r["upstream_newer_than_custom"] for r in rows)


def test_custom_retire_moves_to_retired_folder(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    _make_custom_override(workspace)
    custom_dir = workspace / "custom" / "fetch" / "fetch_world_bank"
    assert custom_dir.exists()
    capsys.readouterr()
    rc = main(["custom", "retire", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    retired_path = Path(payload["retired_to"])
    assert retired_path.exists()
    assert not custom_dir.exists()
    assert retired_path.parent.name == "_retired"


def test_module_compare_lists_modified_files(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    custom = _make_custom_override(workspace)
    # Edit the manifest so it differs from the template (which would be the
    # source template's module.yaml).
    capsys.readouterr()
    rc = main(["module", "compare", "fetch.world_bank", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    diff_paths = {row["path"] for row in payload["diff_files"]}
    assert "module.yaml" in diff_paths  # differs because version is 9.9.9


def test_fetched_data_audit_flags_records_with_no_version(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Save a record WITHOUT setting run-provenance — older fetches won't have it.
    request_state.clear()
    save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw={"rows": [{"v": 1}]},
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at="2026-04-01T12:00:00+00:00",
    )
    capsys.readouterr()
    rc = main(["fetched-data", "audit", "--old-modules", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    findings = payload["findings"]
    # Either "no_version_recorded" or "older_than_installed" — both count as flagged.
    assert findings


def test_fetched_data_audit_passes_when_provenance_matches_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Read installed version and stamp it as run-provenance before saving.
    manifest = yaml.safe_load(
        (workspace / "source" / "fetch" / "fetch_world_bank" / "module.yaml").read_text(encoding="utf-8")
    )
    request_state.set_run_provenance(
        module_version=str(manifest["version"]),
        sancho_version="test",
        module_source="source",
        module_path="test/main.py",
    )
    try:
        save_raw(
            data_raw_path=workspace / "fetched-data",
            module_id="fetch.world_bank",
            family_or_dataset_id="v2.data.country_indicator",
            raw={"rows": [{"v": 1}]},
            params={"format": "json"},
            source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
            fetched_at="2026-04-01T12:00:00+00:00",
        )
    finally:
        request_state.clear()
    capsys.readouterr()
    rc = main(["fetched-data", "audit", "--old-modules", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts_by_status"]["matches_installed"] >= 1
