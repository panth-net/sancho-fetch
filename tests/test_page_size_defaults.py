from __future__ import annotations

from pathlib import Path
from typing import Any

from sancho.cli import main
from sancho.runtime.executor import run_module
from sancho.runtime.page_size import SOCRATA_MAX_LIMIT, WORLD_BANK_MAX_PER_PAGE, apply_max_page_size


def test_max_page_size_helper_applies_world_bank_defaults_without_overriding_user_values() -> None:
    family = {"query_params": {"format": {}, "per_page": {}}}

    defaults = apply_max_page_size(
        {},
        module_id="fetch.world_bank",
        family=family,
        base="v2",
    )
    assert defaults["format"] == "json"
    assert defaults["per_page"] == WORLD_BANK_MAX_PER_PAGE

    explicit = apply_max_page_size(
        {"format": "xml", "per_page": 1000},
        module_id="fetch.world_bank",
        family=family,
        base="v2",
        explicit_keys={"format", "per_page"},
    )
    assert explicit == {"format": "xml", "per_page": 1000}


def test_max_page_size_helper_applies_socrata_limit_only_when_catalog_supports_it() -> None:
    family = {"query_params": {"$limit": {}, "$offset": {}}}

    defaults = apply_max_page_size({}, module_id="fetch.cdc", family=family)
    assert defaults["$limit"] == SOCRATA_MAX_LIMIT

    explicit = apply_max_page_size(
        {"$limit": 25},
        module_id="fetch.nyc_open_data",
        family=family,
        explicit_keys={"$limit"},
    )
    assert explicit["$limit"] == 25

    unsupported = apply_max_page_size({}, module_id="fetch.cdc", family={"query_params": {"q": {}}})
    assert "$limit" not in unsupported


def test_max_page_size_helper_handles_special_endpoint_rules() -> None:
    dc_default = apply_max_page_size({}, module_id="fetch.dc_open_data")
    assert dc_default["resultRecordCount"] == 1000

    dkan_default = apply_max_page_size(
        {},
        module_id="fetch.cms.data",
        endpoint="/data-api/v1/datastore/query/abcd",
    )
    assert dkan_default["limit"] == 500

    dkan_metadata = apply_max_page_size(
        {},
        module_id="fetch.cms.data",
        endpoint="/data.json",
    )
    assert "limit" not in dkan_metadata

    nrel_default = apply_max_page_size(
        {},
        module_id="fetch.nrel.alt_fuel_stations",
        endpoint="/api/alt-fuel-stations/v1.json",
    )
    assert nrel_default["limit"] == "all"


def test_world_bank_runtime_uses_max_page_size_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        captured["params"] = params
        return [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 1}]]

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    result = run_module(
        workspace,
        module_id="fetch.world_bank",
        input_payload={
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
            "params": {},
        },
    )

    assert result.status == "ok"
    assert captured["params"]["format"] == "json"
    assert captured["params"]["per_page"] == WORLD_BANK_MAX_PER_PAGE
    assert result.output["params"]["per_page"] == WORLD_BANK_MAX_PER_PAGE


def test_cdc_runtime_uses_max_soda_limit_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        captured["params"] = params
        return [{"id": "row-1"}]

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.cdc", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    result = run_module(
        workspace,
        module_id="fetch.cdc",
        input_payload={
            "base": "resource",
            "method": "GET",
            "path": "/bi63-dtpu.json",
            "params": {},
        },
    )

    assert result.status == "ok"
    assert captured["params"]["$limit"] == SOCRATA_MAX_LIMIT
    assert result.output["params"]["$limit"] == SOCRATA_MAX_LIMIT
