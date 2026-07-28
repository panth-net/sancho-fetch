from __future__ import annotations

from pathlib import Path

import pytest

from sancho.cli import main

pytestmark = pytest.mark.shape
from sancho.modules import catalog_state_for_module, load_template_registry, validate_manifest_payload
from sancho.runtime.executor import run_module


def test_builtin_template_manifests_validate() -> None:
    registry = load_template_registry()
    assert registry
    for item in registry.values():
        validate_manifest_payload(item.manifest)


def test_catalog_state_reports_large_tier_missing_catalogs(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--yes"]) == 0
    workspace = tmp_path / "sancho-workspace"
    module_dir = tmp_path / "module"
    module_dir.mkdir()

    state, detail = catalog_state_for_module(
        workspace,
        "fetch.example",
        module_dir,
        {"type": "fetch", "catalog_tier": "large"},
    )
    assert state == "not_ready_catalog_missing"
    assert "catalog.json" in detail
    assert "catalog.meta.json" in detail

    (module_dir / "catalog.json").write_text("{}", encoding="utf-8")
    (module_dir / "catalog.meta.json").write_text("{}", encoding="utf-8")
    state, detail = catalog_state_for_module(
        workspace,
        "fetch.example",
        module_dir,
        {"type": "fetch", "catalog_tier": "large"},
    )
    assert state == "ready"
    assert detail == "catalog artifacts available"


def test_catalog_state_reports_small_tier_fetch_still_works(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--yes"]) == 0
    workspace = tmp_path / "sancho-workspace"
    module_dir = tmp_path / "module"
    module_dir.mkdir()

    state, detail = catalog_state_for_module(
        workspace,
        "fetch.small",
        module_dir,
        {"type": "fetch", "catalog_tier": "small"},
    )
    assert state == "ready_without_catalog_but_fetch_still_works"
    assert detail == "catalog_tier=small"


def test_module_entrypoints_smoke(monkeypatch, tmp_path: Path) -> None:
    def _canned(url: str):
        if "api.census.gov" in url:
            return [["NAME", "DP05_0001E"], ["x", "1"]]
        if "api.bls.gov" in url:
            return {"Results": {"series": [{"seriesID": "CUUR0000SA0", "data": []}]}}
        if "api.open.fec.gov" in url:
            return {"results": [{"candidate_id": "P00000001"}]}
        if "api.worldbank.org" in url:
            return [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 1}]]
        if "search.worldbank.org" in url:
            return {"projects": {"P0001": {"id": "P0001"}}}
        if "api.congress.gov" in url:
            return {"bills": [{"number": "1", "title": "Example"}]}
        if "/resource/" in url:
            return [{"id": 1, "value": "row"}]
        return {"ok": True, "url": url}

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        return _canned(url)

    def fake_get_json(url, *, params=None, headers=None, ua=None, timeout=30, max_retries=3, backoff=0.5):
        return _canned(url)

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setattr("sancho.runtime.net.get_json", fake_get_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")

    assert main(["init", "--path", str(tmp_path), "--yes"]) == 0
    workspace = tmp_path / "sancho-workspace"

    module_inputs = {
        "fetch.census.acs_profile": {"geography": "state:06"},
        "fetch.bls": {
            "base": "v2",
            "method": "POST",
            "path": "/timeseries/data/",
            "body": {"seriesid": ["CUUR0000SA0"]},
        },
        "fetch.bea.nipa_table": {"table_name": "T10101"},
        "fetch.hud.fmr": {"url": "https://www.huduser.gov/hudapi/public/fmr/listMetroAreas"},
        "fetch.socrata.dataset": {"domain": "data.seattle.gov", "dataset_id": "kzjm-xkqj"},
        "fetch.treasury.fiscal_data": {},
        "fetch.usaspending.awards": {},
        "fetch.congress.bills": {},
        "fetch.federal_register.documents": {},
        "fetch.regulations.dockets": {},
        "fetch.usgs.earthquakes": {"params": {"format": "geojson", "limit": 10}},
        "fetch.noaa.cdo": {},
        "fetch.eia.series": {},
        "fetch.fbi.crime": {"params": {"from": 2022, "to": 2022}},
        "fetch.nhtsa.recalls": {"params": {"make": "HONDA", "model": "CIVIC", "modelYear": 2020}},
        "fetch.fema.openfema": {"params": {"$top": 10}},
        "fetch.cdc": {
            "base": "resource",
            "method": "GET",
            "path": "/bi63-dtpu.json",
            "params": {"$limit": 10},
        },
        "fetch.cms.data": {"params": {"show-reference-ids": "true"}},
        "fetch.usda.quickstats": {"params": {"format": "JSON", "commodity_desc": "CORN", "year__GE": "2022"}},
        "fetch.socrata.chicago_crimes": {"params": {"$limit": 5}},
        "fetch.nyc_open_data": {
            "base": "nyc_v2",
            "method": "GET",
            "path": "/resource/erm2-nwe9.json",
            "params": {"$limit": 5},
        },
        "fetch.socrata.sf_building_permits": {"params": {"$limit": 5}},
        "fetch.socrata.la_crime": {"params": {"$limit": 5}},
        "fetch.socrata.seattle_building_permits": {"params": {"$limit": 5}},
        "fetch.college_scorecard.schools": {},
        "fetch.naep.adhoc_data": {},
        "fetch.dol.osha_inspections": {},
        "fetch.epa.echo_facilities": {},
        "fetch.epa.aqs_annual": {},
        "fetch.airnow": {},
        "fetch.fdic.institutions": {},
        "fetch.fec": {
            "base": "v1",
            "method": "GET",
            "path": "/candidates/search/",
            "params": {"q": "smith", "per_page": 10},
        },
        "fetch.gsa_calc.ceiling_rates": {},
        "fetch.uspto.application": {},
        "fetch.cfpb.complaints": {},
        "fetch.usda.fooddata_search": {},
        "fetch.sec.company_submissions": {},
        "fetch.clinical_trials.studies": {},
        "fetch.fda.drug_events": {},
        "fetch.doj.press_releases": {},
        "fetch.nrel.alt_fuel_stations": {},
        "fetch.open_payments.datasets": {},
        "fetch.world_bank": {
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
            "params": {"format": "json", "per_page": 1000},
        },
        "process.normalize_records": {"records": [{"Mixed Key": 1}]},
        "analyze.summary": {"records": [{"a": 1}]},
        "dashboard.basic_report": {"title": "Smoke", "metrics": {"x": 1}},
    }

    for module_id in module_inputs:
        assert main(["add", module_id, "--workspace", str(tmp_path)]) == 0

    for module_id, payload in module_inputs.items():
        result = run_module(workspace, module_id=module_id, input_payload=payload)
        assert result.status == "ok"
