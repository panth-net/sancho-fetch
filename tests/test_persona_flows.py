from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main

pytestmark = pytest.mark.e2e


def test_operator_flow_guided(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "y")

    assert main(["init", "--path", str(tmp_path), "--mode", "operator"]) == 0
    assert main(["add", "analyze.summary", "--workspace", str(tmp_path)]) == 0

    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"records": [{"x": 1}]}), encoding="utf-8")

    assert main(["run", "analyze.summary", "--workspace", str(tmp_path), "--input", str(input_file)]) == 0


def test_coder_flow_non_interactive(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "process.normalize_records", "--workspace", str(tmp_path)]) == 0

    input_file = tmp_path / "process_input.json"
    input_file.write_text(json.dumps({"records": [{"A": 1}]}), encoding="utf-8")

    assert main(["run", "process.normalize_records", "--workspace", str(tmp_path), "--input", str(input_file)]) == 0
    assert main(["update", "preview", "process.normalize_records", "--workspace", str(tmp_path)]) == 0


def test_coder_can_install_core_federal_pack(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "pack.core_federal", "--workspace", str(tmp_path)]) == 0

    modules_cfg_path = tmp_path / "sancho-workspace" / "modules.yaml"
    modules_cfg = yaml.safe_load(modules_cfg_path.read_text(encoding="utf-8")) or {}
    installed = set((modules_cfg.get("modules") or {}).keys())

    expected = {
        "fetch.census.acs_profile",
        "fetch.bls",
        "fetch.bea.nipa_table",
        "fetch.hud.fmr",
    }
    assert expected.issubset(installed)


def test_coder_can_install_extended_and_civic_packs(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "pack.federal_extended", "--workspace", str(tmp_path)]) == 0
    assert main(["add", "pack.civic_socrata", "--workspace", str(tmp_path)]) == 0

    modules_cfg_path = tmp_path / "sancho-workspace" / "modules.yaml"
    modules_cfg = yaml.safe_load(modules_cfg_path.read_text(encoding="utf-8")) or {}
    installed = set((modules_cfg.get("modules") or {}).keys())

    expected = {
        "fetch.usda.quickstats",
        "fetch.fema.openfema",
        "fetch.congress.bills",
        "fetch.socrata.dataset",
        "fetch.socrata.chicago_crimes",
        "fetch.cdc",
        "fetch.bls",
    }
    assert expected.issubset(installed)


def test_coder_can_install_federal_research_pack(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "pack.federal_research", "--workspace", str(tmp_path)]) == 0

    modules_cfg_path = tmp_path / "sancho-workspace" / "modules.yaml"
    modules_cfg = yaml.safe_load(modules_cfg_path.read_text(encoding="utf-8")) or {}
    installed = set((modules_cfg.get("modules") or {}).keys())

    expected = {
        "fetch.college_scorecard.schools",
        "fetch.fdic.institutions",
        "fetch.uspto.application",
        "fetch.nrel.alt_fuel_stations",
        "fetch.world_bank",
        "fetch.fec",
    }
    assert expected.issubset(installed)


def test_coder_can_install_new_themed_starter_packs(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "pack.us_housing", "--workspace", str(tmp_path)]) == 0
    assert main(["add", "pack.environment_climate", "--workspace", str(tmp_path)]) == 0

    modules_cfg_path = tmp_path / "sancho-workspace" / "modules.yaml"
    modules_cfg = yaml.safe_load(modules_cfg_path.read_text(encoding="utf-8")) or {}
    installed = set((modules_cfg.get("modules") or {}).keys())

    expected = {
        "fetch.hud.fmr",
        "fetch.census.acs_profile",
        "fetch.nyc_open_data",
        "fetch.noaa.cdo",
        "fetch.epa.aqs_annual",
        "fetch.usgs.earthquakes",
    }
    assert expected.issubset(installed)
