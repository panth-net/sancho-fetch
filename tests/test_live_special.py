"""Live integration tests for large-tier catalog-driven modules and special cases.

Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_special.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from _live_helpers import (
    add_and_run,
    assert_has_rows,
    assert_output_shape,
    assert_raw_saved,
    assert_row_fields,
    init_workspace,
    require_env_key,
    require_live_gate,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_live_gate()
    tmp = tmp_path_factory.mktemp("live_special")
    ws = init_workspace(tmp)
    return ws


# ── Large-tier catalog-driven modules ────────────────────────────────────


def test_live_world_bank(live_ws):
    out = add_and_run(live_ws, "fetch.world_bank", {
        "base": "v2",
        "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
        "params": {"format": "json", "per_page": 5},
    })
    assert_output_shape(out, "provider", "dataset_ref", "rows", "retrieved_at")
    assert out["provider"] == "world_bank"
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.world_bank")


def test_live_world_bank_us_population_5_years(live_ws):
    """US population over 2018-2022 — single country, date range."""
    out = add_and_run(live_ws, "fetch.world_bank", {
        "base": "v2",
        "method": "GET",
        "path": "/country/USA/indicator/SP.POP.TOTL",
        "params": {"format": "json", "per_page": 10, "date": "2018:2022"},
    })
    assert_has_rows(out)
    rows = out["rows"]
    countries = {r.get("country", {}).get("id") for r in rows if isinstance(r, dict)}
    assert countries == {"US"} or "US" in countries, (
        f"expected US-only rows, got countries {countries}"
    )


def test_live_world_bank_gdp_three_countries_2022(live_ws):
    """2022 GDP for US, China, Germany — multi-country with `;` separator."""
    out = add_and_run(live_ws, "fetch.world_bank", {
        "base": "v2",
        "method": "GET",
        "path": "/country/USA;CHN;DEU/indicator/NY.GDP.MKTP.CD",
        "params": {"format": "json", "per_page": 30, "date": "2022"},
    })
    assert_has_rows(out)
    rows = out["rows"]
    countries = {r.get("country", {}).get("id") for r in rows if isinstance(r, dict)}
    assert {"US", "CN", "DE"}.issubset(countries), (
        f"expected US/CN/DE in countries, got {countries}"
    )


def test_live_world_bank_wdi_indicator_list(live_ws):
    """Browse WDI indicators (source ID 2 = WDI)."""
    out = add_and_run(live_ws, "fetch.world_bank", {
        "base": "v2",
        "method": "GET",
        "path": "/indicator",
        "params": {"format": "json", "source": "2", "per_page": 25},
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Each indicator should have an `id` and `name`.
    assert any(
        r.get("id") and r.get("name")
        for r in rows if isinstance(r, dict)
    ), f"expected indicator rows with id/name, got {rows[:2]}"


def test_live_world_bank_kenya_projects(live_ws):
    """World Bank projects in Kenya — companion projects search API."""
    out = add_and_run(live_ws, "fetch.world_bank", {
        "base": "projects_v2",
        "method": "GET",
        "path": "/projects",
        "params": {"format": "json", "rows": 5, "os": 0, "countrycode": "KE"},
    })
    assert_has_rows(out)


def test_live_bls(live_ws):
    out = add_and_run(live_ws, "fetch.bls", {
        "base": "v2_latest",
        "method": "POST",
        "path": "/timeseries/data/",
        "body": {"seriesid": ["CUUR0000SA0"], "latest": True},
    })
    assert_output_shape(out, "provider", "dataset_ref", "rows", "retrieved_at")
    assert out["provider"] == "bls"
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.bls")


def test_live_bls_cpi_recent_data(live_ws):
    """CPI All Urban Consumers data over a multi-year window."""
    out = add_and_run(live_ws, "fetch.bls", {
        "base": "v2",
        "method": "POST",
        "path": "/timeseries/data/",
        "body": {"seriesid": ["CUUR0000SA0"], "startyear": "2023", "endyear": "2024"},
    })
    assert_has_rows(out)
    series = out["rows"][0]
    assert series.get("seriesID") == "CUUR0000SA0"
    data = series.get("data", [])
    assert len(data) >= 12, f"expected >=12 monthly observations, got {len(data)}"


def test_live_bls_unemployment_recent(live_ws):
    """Civilian unemployment rate over a multi-year window."""
    out = add_and_run(live_ws, "fetch.bls", {
        "base": "v2",
        "method": "POST",
        "path": "/timeseries/data/",
        "body": {"seriesid": ["LNS14000000"], "startyear": "2023", "endyear": "2024"},
    })
    assert_has_rows(out)
    series = out["rows"][0]
    assert series.get("seriesID") == "LNS14000000"
    data = series.get("data", [])
    assert len(data) >= 12, f"expected >=12 monthly observations, got {len(data)}"


def test_live_bls_surveys_list(live_ws):
    """List of available BLS surveys (the GET path)."""
    out = add_and_run(live_ws, "fetch.bls", {
        "base": "v2",
        "method": "GET",
        "path": "/surveys",
    })
    assert_has_rows(out)
    assert any(
        isinstance(survey, dict) and "survey_name" in survey
        for survey in out["rows"]
    ), f"expected at least one survey with `survey_name`, got {out['rows'][:3]}"


def test_live_fec(live_ws):
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fec", {
        "base": "v1",
        "method": "GET",
        "path": "/candidates/search/",
        "params": {"q": "smith", "per_page": 5},
    })
    assert_output_shape(out, "provider", "dataset_ref", "rows", "retrieved_at")
    assert out["provider"] == "fec"
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.fec")


def test_live_fec_search_candidates_named_biden(live_ws):
    """Search candidates with 'biden' in name."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fec", {
        "base": "v1",
        "method": "GET",
        "path": "/candidates/search/",
        "params": {"q": "biden", "per_page": 10},
    })
    assert_has_rows(out)
    rows = out["rows"]
    names = [r.get("name", "").lower() for r in rows if isinstance(r, dict)]
    assert any("biden" in n for n in names), (
        f"expected 'biden' in candidate names, got {names[:3]}"
    )


def test_live_fec_super_pacs_2024(live_ws):
    """Super PACs (committee_type O) — exercises type filter."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fec", {
        "base": "v1",
        "method": "GET",
        "path": "/committees/",
        "params": {"committee_type": "O", "per_page": 10},
    })
    assert_has_rows(out)
    rows = out["rows"]
    types = {r.get("committee_type") for r in rows if isinstance(r, dict)}
    assert types == {"O"}, f"expected only Super PAC (O), got {types}"


def test_live_fec_top_candidates_by_receipts_2024(live_ws):
    """Top 2024-cycle candidates by money raised — sort by receipts desc."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fec", {
        "base": "v1",
        "method": "GET",
        "path": "/candidates/totals/",
        "params": {"cycle": 2024, "sort": "-receipts", "per_page": 10},
    })
    assert_has_rows(out)
    rows = out["rows"]
    receipts = [r.get("receipts", 0) for r in rows if isinstance(r, dict)]
    # Should be sorted descending.
    assert receipts == sorted(receipts, reverse=True), f"not sorted desc: {receipts[:3]}"


def test_live_fec_rnc_disbursements_2024(live_ws):
    """RNC (C00075820) largest disbursements in 2024 — committee filter + sort."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fec", {
        "base": "v1",
        "method": "GET",
        "path": "/schedules/schedule_b/",
        "params": {
            "committee_id": "C00075820",
            "two_year_transaction_period": 2024,
            "sort": "-disbursement_amount",
            "per_page": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    committee_ids = {r.get("committee_id") for r in rows if isinstance(r, dict)}
    assert committee_ids == {"C00075820"}, (
        f"expected only RNC committee_id, got {committee_ids}"
    )


# ── Geospatial (requires auth) ───────────────────────────────────────────


def test_live_earthengine(live_ws):
    require_env_key("EARTHENGINE_PROJECT")
    out = add_and_run(live_ws, "fetch.earthengine", {
        "dataset_id": "MODIS/006/MOD13A2",
        "bbox": [-122.5, 37.5, -122.0, 38.0],
        "mode": "raster",
        "reducer": "mean",
        "scale": 1000,
        "date_start": "2024-01-01",
        "date_end": "2024-03-01",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


# ── Skip stubs for modules with custom setup requirements ────────────────


_WVS_FIXTURE_CANDIDATES = [
    Path("Z:/Github_Z/wvs-toolkit/raw-data/wvs/wvs_wave_7_2017-22/WVS_Cross-National_Wave_7_csv_v6_0.zip"),
    Path("Z:/Github_Z/wvs-toolkit/raw-data/wvs/wvs_wave_7_2017-22/WVS_Cross-National_Wave_7_csv_v6_0.csv"),
]


def _wvs_fixture_path() -> str:
    """Return path to a locally-available WVS file, or skip the test."""
    override = os.environ.get("WVS_FIXTURE_PATH")
    if override:
        p = Path(override)
        if p.exists():
            return str(p)
    for candidate in _WVS_FIXTURE_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    pytest.skip(
        "fetch.wvs live test needs a WVS data file (.csv / .csv.zip / .sav). "
        "Set WVS_FIXTURE_PATH or place a copy of the WVS-7 CSV at one of: "
        + ", ".join(str(c) for c in _WVS_FIXTURE_CANDIDATES)
    )


def test_live_wvs_instructions(live_ws):
    """Without file_path, the module returns manual-download instructions."""
    out = add_and_run(live_ws, "fetch.wvs")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert out["dataset_ref"] == "intl_wvs"
    raw = out.get("raw") or {}
    assert raw.get("status") == "manual_download_required"
    assert "worldvaluessurvey.org" in raw.get("instructions", "")


def test_live_wvs_usa_wave7(live_ws):
    """USA respondents in WVS Wave 7 — filter by country=USA, wave=7."""
    fixture = _wvs_fixture_path()
    out = add_and_run(live_ws, "fetch.wvs", {
        "file_path": fixture,
        "country": "USA",
        "wave": 7,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    # WVS-7 USA wave had ~2,596 respondents — sanity check non-trivial size.
    assert len(out["rows"]) >= 1000, (
        f"expected >=1000 USA WVS-7 rows, got {len(out['rows'])}"
    )
    sample = out["rows"][0]
    country_col = next(
        (k for k in sample if k.upper() in ("B_COUNTRY_ALPHA", "C_COW_ALPHA")),
        None,
    )
    assert country_col, f"expected country column in WVS row keys: {list(sample)[:10]}"
    assert str(sample[country_col]).upper() == "USA"


def test_live_wvs_germany_wave7(live_ws):
    """Germany respondents in WVS Wave 7."""
    fixture = _wvs_fixture_path()
    out = add_and_run(live_ws, "fetch.wvs", {
        "file_path": fixture,
        "country": "DEU",
        "wave": 7,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    sample = out["rows"][0]
    country_col = next(
        (k for k in sample if k.upper() in ("B_COUNTRY_ALPHA", "C_COW_ALPHA")),
        None,
    )
    assert country_col
    assert str(sample[country_col]).upper() == "DEU"


def test_live_overture_maps_skip():
    pytest.skip(
        "fetch.overture_maps requires duckdb with spatial extension + S3/Azure access. "
        "Install duckdb and run manually."
    )
