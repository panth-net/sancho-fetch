from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.cli_module_inspect import _filter_variables
from sancho.constants import WORKSPACE_DIRNAME

# A minimal stand-in for a Census variables.json payload. Includes a geography
# predicate ("for") that must be filtered out, and "!!" label separators that
# must be normalized.
FAKE_VARIABLES = {
    "variables": {
        "NAME": {"label": "Geography", "concept": "Selectable Geographies"},
        "DP05_0001E": {
            "label": "Estimate!!SEX AND AGE!!Total population",
            "concept": "ACS Demographic and Housing Estimates",
            "group": "DP05",
            "predicateType": "int",
        },
        "DP05_0047E": {
            "label": "Estimate!!RACE!!Total population!!One race!!Asian",
            "concept": "ACS Demographic and Housing Estimates",
            "group": "DP05",
            "predicateType": "int",
        },
        "for": {"label": "Census API FIPS 'for' clause"},
    }
}


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_module_variables_lists_datasets(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    # Falls back to the template catalog without installing the module or hitting
    # the network -- omitting --dataset is dataset discovery.
    _init_workspace(tmp_path)
    capsys.readouterr()  # drain the "Initialized workspace" line
    rc = main([
        "module", "variables", "fetch.census.acs_profile",
        "--search", "5-year data profile",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "datasets"
    assert payload["zone"] == "template"
    assert any(d["dataset"] == "ACSDP5Y2023" for d in payload["datasets"])


def test_module_variables_dataset_discovery_seeds_from_module_id(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Without --search, the ~1,800-dataset catalog is filtered by the module
    # id's own tokens and sorted newest-first, so the relevant family surfaces
    # instead of decades of unrelated datasets.
    _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main([
        "module", "variables", "fetch.census.acs_profile",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["implicit_search"] == "acs profile"
    shown = [d["dataset"] for d in payload["datasets"]]
    assert shown and any(ds.startswith("ACSDP") for ds in shown[:5])
    temporals = [str(d.get("temporal") or "") for d in payload["datasets"]]
    assert temporals == sorted(temporals, reverse=True)


def test_module_variables_resolves_codes_without_guessing(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_workspace(tmp_path)
    calls: list[str] = []

    def fake_get_json(url: str, **kwargs: object) -> dict:
        calls.append(url)
        return FAKE_VARIABLES

    monkeypatch.setattr("sancho.runtime.net.get_json", fake_get_json)
    capsys.readouterr()  # drain the "Initialized workspace" line
    rc = main([
        "module", "variables", "fetch.census.acs_profile",
        "--dataset", "ACSDP5Y2023", "--search", "asian",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "variables"
    assert payload["dataset"] == "ACSDP5Y2023"
    assert payload["variables_url"].endswith("/variables.json")
    assert payload["source"] == "live"
    codes = {v["code"] for v in payload["variables"]}
    assert "DP05_0047E" in codes  # the code the agent had to guess
    assert "for" not in codes  # geography predicate filtered out
    # Labels are normalized from the Census "!!" separator.
    asian = next(v for v in payload["variables"] if v["code"] == "DP05_0047E")
    assert "!!" not in asian["label"] and "Asian" in asian["label"]
    assert len(calls) == 1


def test_module_variables_uses_cache_on_second_call(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_workspace(tmp_path)
    calls: list[str] = []

    def fake_get_json(url: str, **kwargs: object) -> dict:
        calls.append(url)
        return FAKE_VARIABLES

    monkeypatch.setattr("sancho.runtime.net.get_json", fake_get_json)
    args = [
        "module", "variables", "fetch.census.acs_profile",
        "--dataset", "ACSDP5Y2023", "--code", "DP05_0047E",
        "--workspace", str(tmp_path), "--json",
    ]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "cache"
    assert len(calls) == 1  # network hit only on the first call


def test_module_variables_documented_codes_fallback_no_dead_end(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # A module with no catalog and no codebook URL (e.g. fetch.vdem) must serve
    # its documented input fields instead of dead-ending.
    _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main([
        "module", "variables", "fetch.vdem",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "documented_codes"
    fields = {f["field"] for f in payload["fields"]}
    assert "indicators" in fields
    assert payload["hint"]  # tells the agent what to do instead of guessing


def test_module_variables_unknown_dataset_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    rc = main([
        "module", "variables", "fetch.census.acs_profile",
        "--dataset", "NOPE_NOT_A_DATASET",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 1


def test_filter_variables_word_boundary_and_ranking() -> None:
    rows = [
        {"code": "DP05_0018E", "label": "SEX AND AGE > Median age", "concept": "", "group": "", "predicateType": ""},
        {"code": "DP04_0101E", "label": "Owner costs as a percentage of income", "concept": "", "group": "", "predicateType": ""},
        {"code": "DP05_0001E", "label": "SEX AND AGE > Total population", "concept": "", "group": "", "predicateType": ""},
    ]
    # "age" must NOT match "percentage" (whole-word matching).
    by_age = _filter_variables(rows, search="age", code=None)
    codes = {r["code"] for r in by_age}
    assert "DP05_0018E" in codes
    assert "DP04_0101E" not in codes  # 'percentAGE' is not a match
    # "median age" ranks the real Median age variable first.
    ranked = _filter_variables(rows, search="median age", code=None)
    assert ranked[0]["code"] == "DP05_0018E"


def test_filter_variables_partial_match_fallback() -> None:
    rows = [
        {"code": "X1", "label": "Food security status", "concept": "", "group": "", "predicateType": ""},
        {"code": "X2", "label": "Housing cost burden", "concept": "", "group": "", "predicateType": ""},
    ]
    # No row matches BOTH "food" and "scarcity" -> fall back to best partial match
    # so the agent gets a candidate instead of an empty result to guess from.
    res = _filter_variables(rows, search="food scarcity", code=None)
    assert res and res[0]["code"] == "X1"
    # A query that matches nothing at all still returns nothing.
    assert _filter_variables(rows, search="zzz qqq", code=None) == []


def test_module_variables_uses_manifest_codebook_url(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # census.decennial declares a codebook.url_template (no catalog.json). The
    # command must fetch + parse it. We mock the network with a fake Census dict.
    _init_workspace(tmp_path)
    fake = {"variables": {
        "P3_002N": {"label": "Total!!White alone", "concept": "RACE", "group": "P3"},
        "for": {"label": "geography clause"},
    }}

    def fake_get_json(url, **kwargs):
        assert url.endswith("/variables.json"), url  # year/dataset filled into template
        assert "/2020/dec/dhc/" in url
        return fake

    monkeypatch.setattr("sancho.runtime.net.get_json", fake_get_json)
    capsys.readouterr()
    rc = main([
        "module", "variables", "fetch.census.decennial",
        "--search", "white alone",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "variables"
    assert payload["source"] == "live"
    codes = {v["code"] for v in payload["variables"]}
    assert "P3_002N" in codes
    assert "for" not in codes


def test_module_variables_surfaces_bundled_codebook(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Providers whose catalog has no DCAT `datasets` list ship their codebook
    # directly (e.g. nhtsa `vehicle_variables`). No network, no dataset arg.
    _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main([
        "module", "variables", "fetch.nhtsa.recalls",
        "--search", "battery",
        "--workspace", str(tmp_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "bundled_codebook"
    sections = {s["section"] for s in payload["sections"]}
    assert "vehicle_variables" in sections
    # Every shown section actually matched the search term.
    for s in payload["sections"]:
        assert s["items"]
        assert any("battery" in json.dumps(item).lower() for item in s["items"])
