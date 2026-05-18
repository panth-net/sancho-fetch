"""Live integration tests for modules that REQUIRE an API key.

Tests skip gracefully if the required key is not set in the environment.
Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_keyed.py -v
"""

from __future__ import annotations

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
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_env_key("FRED_API_KEY")  # gate on at least one key existing
    tmp = tmp_path_factory.mktemp("live_keyed")
    ws = init_workspace(tmp)
    return ws


# ── FRED ─────────────────────────────────────────────────────────────────


def test_live_fred_series(live_ws):
    require_env_key("FRED_API_KEY")
    out = add_and_run(live_ws, "fetch.fred.series", {
        "series_id": "CPIAUCSL",
        "observation_start": "2024-01-01",
    })
    assert_output_shape(out, "dataset_ref", "series_id", "observations", "retrieved_at")
    assert out["dataset_ref"] == "usgov_fred"
    assert out["series_id"] == "CPIAUCSL"
    assert_has_rows(out, key="observations")
    obs = out["observations"][0]
    assert "date" in obs
    assert "value" in obs
    assert_raw_saved(live_ws, "fetch.fred.series")


def test_live_fred_series_cpi_yoy_pct_change(live_ws):
    """Year-over-year percent change of CPI — exercises the `units` param."""
    require_env_key("FRED_API_KEY")
    out = add_and_run(live_ws, "fetch.fred.series", {
        "series_id": "CPIAUCSL",
        "observation_start": "2023-01-01",
        "units": "pc1",
    })
    assert_has_rows(out, key="observations")
    # YoY change values are typically -5 to +20; raw CPI levels are ~250-400.
    # If `units=pc1` was honored, every value should be in single digits.
    sample_vals = [
        float(obs["value"]) for obs in out["observations"][:3]
        if obs.get("value") not in (".", None, "")
    ]
    assert sample_vals, "expected at least one numeric observation"
    assert all(abs(v) < 50 for v in sample_vals), (
        f"expected YoY percent values, got {sample_vals} (units=pc1 not honored?)"
    )


def test_live_fred_series_unemployment_quarterly(live_ws):
    """Quarterly resampling — exercises `frequency` + `aggregation_method`."""
    require_env_key("FRED_API_KEY")
    out = add_and_run(live_ws, "fetch.fred.series", {
        "series_id": "UNRATE",
        "observation_start": "2020-01-01",
        "frequency": "q",
        "aggregation_method": "avg",
    })
    assert_has_rows(out, key="observations")
    obs_dates = [obs["date"] for obs in out["observations"]]
    # Quarterly observations land on Jan/Apr/Jul/Oct first day. Monthly source
    # data would have all months. If `frequency=q` was honored, only quarter
    # months appear.
    quarter_months = {"01", "04", "07", "10"}
    months_seen = {d.split("-")[1] for d in obs_dates}
    assert months_seen.issubset(quarter_months), (
        f"expected quarterly observations only, got months {months_seen}"
    )


def test_live_fred_series_gdp_recent(live_ws):
    """Default-units fetch of GDP — verifies the simple path still works."""
    require_env_key("FRED_API_KEY")
    out = add_and_run(live_ws, "fetch.fred.series", {
        "series_id": "GDP",
        "observation_start": "2019-01-01",
    })
    assert_has_rows(out, key="observations")
    # GDP is published quarterly in trillions of dollars; values should be
    # in the 20000+ range (raw level).
    sample_vals = [
        float(obs["value"]) for obs in out["observations"][-3:]
        if obs.get("value") not in (".", None, "")
    ]
    assert sample_vals, "expected at least one numeric observation"
    assert all(v > 10000 for v in sample_vals), (
        f"expected GDP raw level (>10000), got {sample_vals}"
    )


# ── BEA ──────────────────────────────────────────────────────────────────


def test_live_bea_nipa_table(live_ws):
    require_env_key("BEA_API_KEY")
    out = add_and_run(live_ws, "fetch.bea.nipa_table", {
        "table_name": "T10101",
    })
    assert_output_shape(out, "dataset_ref", "table_name", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.bea.nipa_table")


def test_live_bea_nipa_table_gdp_annual_recent(live_ws):
    """GDP table T10101 across a multi-year window."""
    require_env_key("BEA_API_KEY")
    out = add_and_run(live_ws, "fetch.bea.nipa_table", {
        "table_name": "T10101",
        "year": "2020,2021,2022,2023,2024",
        "frequency": "A",
    })
    assert_has_rows(out)
    years = {row.get("TimePeriod") for row in out["rows"] if isinstance(row, dict)}
    # Expect at least 3 distinct years in the multi-year payload.
    valid_years = {y for y in years if isinstance(y, str)}
    assert len(valid_years) >= 3, f"expected >=3 distinct years, got {valid_years}"


def test_live_bea_nipa_table_real_gdp_quarterly(live_ws):
    """Real GDP (chained dollars) on a quarterly basis."""
    require_env_key("BEA_API_KEY")
    out = add_and_run(live_ws, "fetch.bea.nipa_table", {
        "table_name": "T10106",
        "year": "2024",
        "frequency": "Q",
    })
    assert_has_rows(out)
    periods = {row.get("TimePeriod") for row in out["rows"] if isinstance(row, dict)}
    assert any(isinstance(p, str) and "Q" in p for p in periods), (
        f"expected quarterly TimePeriod (e.g. '2024Q1'), got {list(periods)[:5]}"
    )


def test_live_bea_nipa_table_personal_income_recent(live_ws):
    """Personal income table T20100 over a multi-year window."""
    require_env_key("BEA_API_KEY")
    out = add_and_run(live_ws, "fetch.bea.nipa_table", {
        "table_name": "T20100",
        "year": "2020,2021,2022,2023,2024",
        "frequency": "A",
    })
    assert_has_rows(out)


# ── Census ───────────────────────────────────────────────────────────────


def test_live_census_acs_profile(live_ws):
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.acs_profile", {
        "geography": "state:06",
        "variables": ["DP05_0001E"],
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.census.acs_profile")


def test_live_census_acs_profile_vienna_va_place(live_ws):
    """The Vienna case — sub-state place query that requires `in_geography`."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.acs_profile", {
        "geography": "place:81072",
        "in_geography": "state:51",
        "variables": ["NAME", "DP05_0001E"],
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    rows = out["rows"]
    # First row is the header; subsequent rows are data.
    assert len(rows) >= 2, f"expected header + >=1 data row, got {len(rows)}"
    header = rows[0]
    name_idx = header.index("NAME")
    data_rows = rows[1:]
    assert any("Vienna" in row[name_idx] for row in data_rows), (
        f"expected at least one row with NAME containing 'Vienna', got {data_rows}"
    )


def test_live_census_acs_profile_california_state(live_ws):
    """State-level query — no `in_geography` needed."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.acs_profile", {
        "geography": "state:06",
        "variables": ["NAME", "DP05_0001E"],
    })
    assert_has_rows(out)
    rows = out["rows"]
    header = rows[0]
    name_idx = header.index("NAME")
    data_rows = rows[1:]
    assert any("California" in row[name_idx] for row in data_rows), (
        f"expected NAME containing 'California', got {data_rows}"
    )


def test_live_census_acs_profile_fairfax_va_county(live_ws):
    """Sub-state county query — requires `in_geography`."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.acs_profile", {
        "geography": "county:059",
        "in_geography": "state:51",
        "variables": ["NAME", "DP05_0001E"],
    })
    assert_has_rows(out)
    rows = out["rows"]
    header = rows[0]
    name_idx = header.index("NAME")
    data_rows = rows[1:]
    assert any("Fairfax" in row[name_idx] for row in data_rows), (
        f"expected NAME containing 'Fairfax', got {data_rows}"
    )


# ── Census Decennial (P1 health source) ────────────────────────────────


def test_live_census_decennial_state_virginia(live_ws):
    """Total population of Virginia from the 2020 DHC."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.decennial", {
        "geography": "state:51",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    rows = out["rows"]
    assert isinstance(rows, list) and len(rows) >= 2, (
        f"expected header + 1 data row, got {rows!r}"
    )
    header = rows[0]
    data = rows[1]
    assert "P1_001N" in header
    pop_col = header.index("P1_001N")
    pop = int(data[pop_col])
    # Virginia 2020 population: 8,631,393
    assert 8_500_000 < pop < 9_000_000, f"VA 2020 pop should be ~8.6M, got {pop}"


def test_live_census_decennial_vienna_va(live_ws):
    """Vienna town, VA — verify the Vienna gotcha works for Decennial too."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.decennial", {
        "geography": "place:81072",
        "in_geography": "state:51",
    })
    rows = out["rows"]
    assert len(rows) >= 2
    name_col = rows[0].index("NAME")
    pop_col = rows[0].index("P1_001N")
    name = rows[1][name_col]
    pop = int(rows[1][pop_col])
    assert "Vienna" in name, f"expected Vienna in name, got {name!r}"
    # Vienna town 2020 DHC pop: 16,473
    assert 16_000 < pop < 17_000, f"Vienna 2020 pop should be ~16.5K, got {pop}"


def test_live_census_decennial_all_states(live_ws):
    """Total population of all 50 states + DC + PR (52 rows)."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.decennial", {
        "geography": "state:*",
    })
    rows = out["rows"]
    # Header + 52 (50 states + DC + PR) = 53 rows
    assert len(rows) >= 51, f"expected 50+ states, got {len(rows)} rows"


def test_live_census_decennial_redistricting_vermont(live_ws):
    """2020 PL94-171 redistricting data for Vermont."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.decennial", {
        "geography": "state:50",
        "dataset": "pl",
    })
    rows = out["rows"]
    assert len(rows) >= 2
    pop_col = rows[0].index("P1_001N")
    pop = int(rows[1][pop_col])
    # Vermont 2020 pop: ~643K
    assert 600_000 < pop < 700_000, f"VT 2020 pop should be ~643K, got {pop}"


def test_live_census_decennial_counties_in_vermont(live_ws):
    """Population of every county in Vermont (14 counties)."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.decennial", {
        "geography": "county:*",
        "in_geography": "state:50",
    })
    rows = out["rows"]
    # Header + 14 Vermont counties = 15 rows
    assert len(rows) >= 14, f"expected 14+ VT counties, got {len(rows) - 1}"


# ── Census Household Pulse Survey (HTOPS, P1 health source) ─────────────


def test_live_census_htops_us_total_2023(live_ws):
    """HPS total population universe for 2023 (US national)."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.htops", {
        "variables": ["UNITS_TOTAL"],
        "time": "2023",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    rows = out["rows"]
    assert isinstance(rows, list) and len(rows) >= 2
    header = rows[0]
    assert "WEEK" in header and "UNITS_TOTAL" in header
    units_col = header.index("UNITS_TOTAL")
    # 2023 universe should be ~250M+ adults
    units = int(rows[1][units_col])
    assert units > 200_000_000, f"expected 200M+ universe, got {units}"


def test_live_census_htops_expense_pressure_2023(live_ws):
    """Adults reporting expense pressure (EXPENSE_TOTAL) in 2023."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.htops", {
        "variables": ["EXPENSE_TOTAL"],
        "time": "2023",
    })
    rows = out["rows"]
    assert len(rows) >= 2
    expense_col = rows[0].index("EXPENSE_TOTAL")
    # At least one week should have a non-null EXPENSE_TOTAL value
    expense_values = [r[expense_col] for r in rows[1:] if r[expense_col] not in (None, "")]
    assert expense_values, "expected at least one non-null EXPENSE_TOTAL"
    # Expense pressure is tens-of-millions of adults
    expense = int(expense_values[0])
    assert expense > 50_000_000, f"expected 50M+ adults reporting expense pressure, got {expense}"


def test_live_census_htops_virginia_universe_2023(live_ws):
    """HPS universe for Virginia (state:51) in 2023."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.htops", {
        "variables": ["UNITS_TOTAL"],
        "time": "2023",
        "geography": "state:51",
    })
    rows = out["rows"]
    assert len(rows) >= 2
    state_col = rows[0].index("state")
    units_col = rows[0].index("UNITS_TOTAL")
    # All rows should be for state 51 (Virginia)
    assert all(r[state_col] == "51" for r in rows[1:]), (
        f"expected all VA rows, got states {[r[state_col] for r in rows[1:5]]}"
    )
    # Virginia adult population ~6.6M
    units = int(rows[1][units_col])
    assert 5_000_000 < units < 8_000_000, f"VA HPS universe should be ~6.6M, got {units}"


def test_live_census_htops_all_states_universe_2023(live_ws):
    """HPS universe size for every state in 2023."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.htops", {
        "variables": ["UNITS_TOTAL"],
        "time": "2023",
        "geography": "state:*",
    })
    rows = out["rows"]
    # At least 50 states × multiple weeks of data; expect many hundreds of rows
    assert len(rows) > 50, f"expected many state rows, got {len(rows)}"


def test_live_census_htops_foodassis_range(live_ws):
    """FOODASSIS_RATE across 2022-2024."""
    require_env_key("CENSUS_API_KEY")
    out = add_and_run(live_ws, "fetch.census.htops", {
        "variables": ["FOODASSIS_RATE"],
        "time": "from 2022 to 2024",
    })
    rows = out["rows"]
    assert len(rows) >= 2, f"expected multiple weeks of HPS data, got {len(rows)}"
    # Time column must span multiple years
    time_col = rows[0].index("time")
    years = {r[time_col] for r in rows[1:]}
    assert len(years) >= 2, f"expected multiple years, got {years}"


# ── Congress ─────────────────────────────────────────────────────────────


def test_live_congress_bills(live_ws):
    require_env_key("CONGRESS_API_KEY")
    # Note: do NOT pass params — let the module's format=json default take effect
    out = add_and_run(live_ws, "fetch.congress.bills", {
        "params": {"format": "json", "limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["congress", "type"])


def test_live_congress_bills_house_bills_118th(live_ws):
    """Latest House bills from the 118th Congress."""
    require_env_key("CONGRESS_API_KEY")
    out = add_and_run(live_ws, "fetch.congress.bills", {
        "endpoint": "https://api.congress.gov/v3/bill/118/hr",
        "params": {"limit": 10, "sort": "updateDate desc"},
    })
    assert_has_rows(out)
    rows = out["rows"]
    # All bills should be congress=118 and type=HR.
    assert all(
        r.get("congress") == 118 and r.get("type") == "HR"
        for r in rows if isinstance(r, dict)
    ), f"expected 118th HR bills, got {[(r.get('congress'), r.get('type')) for r in rows[:3]]}"


def test_live_congress_bills_january_2024_window(live_ws):
    """Bills updated in January 2024 — date window."""
    require_env_key("CONGRESS_API_KEY")
    out = add_and_run(live_ws, "fetch.congress.bills", {
        "endpoint": "https://api.congress.gov/v3/bill",
        "params": {
            "limit": 25,
            "fromDateTime": "2024-01-01T00:00:00Z",
            "toDateTime": "2024-01-31T23:59:59Z",
            "sort": "updateDate desc",
        },
    })
    assert_has_rows(out)


def test_live_congress_bills_current_members(live_ws):
    """Current members of Congress — different resource."""
    require_env_key("CONGRESS_API_KEY")
    out = add_and_run(live_ws, "fetch.congress.bills", {
        "endpoint": "https://api.congress.gov/v3/member",
        "params": {"currentMember": "true", "limit": 25},
    })
    assert_has_rows(out)


def test_live_congress_bills_committees_list(live_ws):
    """List of Congressional committees."""
    require_env_key("CONGRESS_API_KEY")
    out = add_and_run(live_ws, "fetch.congress.bills", {
        "endpoint": "https://api.congress.gov/v3/committee",
        "params": {"limit": 25},
    })
    assert_has_rows(out)


# ── NOAA ─────────────────────────────────────────────────────────────────


def test_live_noaa_cdo(live_ws):
    require_env_key("NOAA_API_TOKEN")
    out = add_and_run(live_ws, "fetch.noaa.cdo", {
        "endpoint": "https://www.ncei.noaa.gov/cdo-web/api/v2/datasets",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["id", "name"])


def test_live_noaa_cdo_list_datasets(live_ws):
    """List NOAA CDO datasets — catalog browse."""
    require_env_key("NOAA_API_TOKEN")
    out = add_and_run(live_ws, "fetch.noaa.cdo", {
        "endpoint": "https://www.ncei.noaa.gov/cdo-web/api/v2/datasets",
        "params": {"limit": 10},
    })
    assert_has_rows(out)
    rows = out["rows"]
    ids = {r.get("id") for r in rows if isinstance(r, dict)}
    assert "GHCND" in ids, f"expected GHCND in datasets, got {ids}"


def test_live_noaa_cdo_boston_stations(live_ws):
    """GHCND weather stations in Boston metro — locationid filter."""
    require_env_key("NOAA_API_TOKEN")
    out = add_and_run(live_ws, "fetch.noaa.cdo", {
        "endpoint": "https://www.ncei.noaa.gov/cdo-web/api/v2/stations",
        "params": {
            "datasetid": "GHCND",
            "locationid": "CITY:US250003",
            "limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Each station has id starting with GHCND:
    ids = [r.get("id", "") for r in rows if isinstance(r, dict)]
    assert all(i.startswith("GHCND:") for i in ids), (
        f"expected GHCND-prefixed IDs, got {ids[:3]}"
    )


def test_live_noaa_cdo_logan_airport_precipitation_june_2024(live_ws):
    """Daily precipitation at Boston Logan Airport for June 1-7 2024 — /data endpoint."""
    require_env_key("NOAA_API_TOKEN")
    out = add_and_run(live_ws, "fetch.noaa.cdo", {
        "endpoint": "https://www.ncei.noaa.gov/cdo-web/api/v2/data",
        "params": {
            "datasetid": "GHCND",
            "stationid": "GHCND:USW00014739",
            "datatypeid": "PRCP",
            "startdate": "2024-06-01",
            "enddate": "2024-06-07",
            "limit": 50,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # All rows should be PRCP datatype, all from Logan station.
    assert all(
        r.get("datatype") == "PRCP" and r.get("station") == "GHCND:USW00014739"
        for r in rows if isinstance(r, dict)
    ), f"expected PRCP at Logan, got {rows[:2]}"


def test_live_noaa_cdo_location_categories(live_ws):
    """List of NOAA location categories — different family."""
    require_env_key("NOAA_API_TOKEN")
    out = add_and_run(live_ws, "fetch.noaa.cdo", {
        "endpoint": "https://www.ncei.noaa.gov/cdo-web/api/v2/locationcategories",
        "params": {"limit": 25},
    })
    assert_has_rows(out)
    rows = out["rows"]
    ids = {r.get("id") for r in rows if isinstance(r, dict)}
    # Should include CITY, ZIP, FIPS at minimum.
    assert {"CITY", "ZIP"}.issubset(ids), f"expected CITY/ZIP in categories, got {ids}"


# ── HUD ──────────────────────────────────────────────────────────────────


def test_live_hud_fmr(live_ws):
    require_env_key("HUD_API_TOKEN")
    out = add_and_run(live_ws, "fetch.hud.fmr", {
        "url": "https://www.huduser.gov/hudapi/public/fmr/listMetroAreas",
    })
    assert_output_shape(out, "dataset_ref", "raw", "retrieved_at")
    # HUD returns either a list (listMetroAreas) or a dict
    raw = out.get("raw")
    assert raw, "HUD returned empty raw response"
    if isinstance(raw, list):
        assert len(raw) > 0, "HUD metro areas list is empty"
    elif isinstance(raw, dict):
        assert any(raw.values()), "HUD dict response has no values"
    assert_raw_saved(live_ws, "fetch.hud.fmr")


def test_live_hud_list_metro_areas(live_ws):
    """List all FMR metro areas."""
    require_env_key("HUD_API_TOKEN")
    out = add_and_run(live_ws, "fetch.hud.fmr", {
        "url": "https://www.huduser.gov/hudapi/public/fmr/listMetroAreas",
    })
    raw = out.get("raw")
    assert isinstance(raw, list) and len(raw) >= 100, f"expected >=100 metros, got {len(raw) if isinstance(raw, list) else type(raw).__name__}"


def test_live_hud_counties_in_california(live_ws):
    """All FMR counties in California."""
    require_env_key("HUD_API_TOKEN")
    out = add_and_run(live_ws, "fetch.hud.fmr", {
        "url": "https://www.huduser.gov/hudapi/public/fmr/listCounties/CA",
    })
    raw = out.get("raw")
    assert isinstance(raw, list) and len(raw) > 30, f"expected many CA counties, got {len(raw) if isinstance(raw, list) else 'non-list'}"


def test_live_hud_dc_metro_fmr_2024(live_ws):
    """2024 Fair Market Rents for DC metro area (METRO47900M47900)."""
    require_env_key("HUD_API_TOKEN")
    out = add_and_run(live_ws, "fetch.hud.fmr", {
        "url": "https://www.huduser.gov/hudapi/public/fmr/data/METRO47900M47900?year=2024",
    })
    raw = out.get("raw")
    assert isinstance(raw, dict) and raw.get("data"), f"expected data envelope, got {type(raw).__name__}"


def test_live_hud_california_income_limits_2024(live_ws):
    """2024 Section 8 income limits for California — different family (/il/...)."""
    require_env_key("HUD_API_TOKEN")
    out = add_and_run(live_ws, "fetch.hud.fmr", {
        "url": "https://www.huduser.gov/hudapi/public/il/statedata/CA?year=2024",
    })
    raw = out.get("raw")
    assert isinstance(raw, dict) and raw.get("data"), f"expected data envelope, got {type(raw).__name__}"


# ── EIA ──────────────────────────────────────────────────────────────────


def test_live_eia_series(live_ws):
    require_env_key("EIA_API_KEY")
    out = add_and_run(live_ws, "fetch.eia.series", {
        "endpoint": "https://api.eia.gov/v2/seriesid/PET.RWTC.D",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_eia_series_wti_crude_daily(live_ws):
    """Daily WTI crude oil price across Q1 2024 — legacy series ID lookup."""
    require_env_key("EIA_API_KEY")
    out = add_and_run(live_ws, "fetch.eia.series", {
        "endpoint": "https://api.eia.gov/v2/seriesid/PET.RWTC.D",
        "params": {"start": "2024-01-01", "end": "2024-03-31"},
    })
    assert_has_rows(out)
    # Daily prices for Q1 2024 should have ~60+ business days.
    assert len(out["rows"]) >= 50, f"expected >=50 daily prices, got {len(out['rows'])}"


def test_live_eia_series_electricity_generation_annual(live_ws):
    """Annual US electricity generation by fuel source — v2 facet query."""
    require_env_key("EIA_API_KEY")
    out = add_and_run(live_ws, "fetch.eia.series", {
        "endpoint": "https://api.eia.gov/v2/electricity/electric-power-operational-data/data/",
        "params": {
            "frequency": "annual",
            "data[0]": "generation",
            "facets[location][]": "US",
            "start": "2020",
            "end": "2023",
        },
    })
    assert_has_rows(out)
    # Should return generation values, distinct fueltypes per year.
    fueltypes = {row.get("fueltypeid") for row in out["rows"] if isinstance(row, dict)}
    valid = {f for f in fueltypes if f}
    assert len(valid) >= 3, f"expected >=3 distinct fueltypes, got {valid}"


def test_live_eia_series_natural_gas_production_monthly(live_ws):
    """Monthly natural gas marketed production for 2023."""
    require_env_key("EIA_API_KEY")
    out = add_and_run(live_ws, "fetch.eia.series", {
        "endpoint": "https://api.eia.gov/v2/natural-gas/prod/sum/data/",
        "params": {
            "frequency": "monthly",
            "data[0]": "value",
            "start": "2023-01",
            "end": "2023-12",
            "length": 100,
        },
    })
    assert_has_rows(out)
    periods = {row.get("period") for row in out["rows"] if isinstance(row, dict)}
    valid_periods = {p for p in periods if isinstance(p, str)}
    assert len(valid_periods) >= 6, (
        f"expected >=6 distinct months in 2023, got {valid_periods}"
    )


def test_live_eia_series_crude_oil_imports_recent(live_ws):
    """US crude oil import volumes by month — pagination via `length`."""
    require_env_key("EIA_API_KEY")
    out = add_and_run(live_ws, "fetch.eia.series", {
        "endpoint": "https://api.eia.gov/v2/petroleum/move/imp/data/",
        "params": {
            "frequency": "monthly",
            "data[0]": "value",
            "start": "2024-01",
            "end": "2024-06",
            "length": 50,
        },
    })
    assert_has_rows(out)
    # Pagination cap respected.
    assert len(out["rows"]) <= 50, f"length=50 not honored: {len(out['rows'])} rows"


# ── USDA ─────────────────────────────────────────────────────────────────


def test_live_usda_quickstats(live_ws):
    require_env_key("USDA_NASS_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.quickstats", {
        "params": {"commodity_desc": "CORN", "year": "2023", "format": "JSON"},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_usda_quickstats_corn_national_2024(live_ws):
    """National CORN statistics for 2024."""
    require_env_key("USDA_NASS_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.quickstats", {
        "params": {
            "commodity_desc": "CORN",
            "year": "2024",
            "agg_level_desc": "NATIONAL",
            "format": "JSON",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    commodities = {r.get("commodity_desc") for r in rows if isinstance(r, dict)}
    assert commodities == {"CORN"}, f"expected CORN only, got {commodities}"


def test_live_usda_quickstats_iowa_corn_production_5yr(live_ws):
    """Iowa CORN grain production over 5 years — state + multi-year + statistic."""
    require_env_key("USDA_NASS_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.quickstats", {
        "params": {
            "commodity_desc": "CORN",
            "state_alpha": "IA",
            "year__GE": "2020",
            "agg_level_desc": "STATE",
            "short_desc": "CORN, GRAIN - PRODUCTION, MEASURED IN BU",
            "format": "JSON",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    states = {r.get("state_alpha") for r in rows if isinstance(r, dict)}
    assert states == {"IA"}, f"expected IA only, got {states}"


def test_live_usda_quickstats_kansas_wheat_county_2023(live_ws):
    """Kansas county-level WHEAT for 2023."""
    require_env_key("USDA_NASS_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.quickstats", {
        "params": {
            "commodity_desc": "WHEAT",
            "state_alpha": "KS",
            "agg_level_desc": "COUNTY",
            "year": "2023",
            "format": "JSON",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    levels = {r.get("agg_level_desc") for r in rows if isinstance(r, dict)}
    assert levels == {"COUNTY"}, f"expected COUNTY only, got {levels}"


def test_live_usda_quickstats_soybeans_national_2024(live_ws):
    """National SOYBEANS for 2024."""
    require_env_key("USDA_NASS_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.quickstats", {
        "params": {
            "commodity_desc": "SOYBEANS",
            "year": "2024",
            "agg_level_desc": "NATIONAL",
            "format": "JSON",
        },
    })
    assert_has_rows(out)


# ── EPA AQS / AirNow ─────────────────────────────────────────────────────


def test_live_epa_aqs_annual(live_ws):
    require_env_key("AQS_API_KEY")
    require_env_key("AQS_EMAIL")
    # AQS annualData/byState requires state/bdate/edate/param. Use CA ozone 2022.
    out = add_and_run(live_ws, "fetch.epa.aqs_annual", {
        "params": {
            "state": "06",
            "bdate": "20220101",
            "edate": "20221231",
            "param": "44201",
        },
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_epa_aqs_california_pm25_2023(live_ws):
    """California 2023 annual PM2.5 (param 88101)."""
    require_env_key("AQS_API_KEY")
    require_env_key("AQS_EMAIL")
    out = add_and_run(live_ws, "fetch.epa.aqs_annual", {
        "endpoint": "https://aqs.epa.gov/data/api/annualData/byState",
        "params": {
            "param": "88101",
            "bdate": "20230101",
            "edate": "20231231",
            "state": "06",
        },
    })
    assert_has_rows(out)


def test_live_epa_aqs_states_list(live_ws):
    """List of all US states with AQS coverage."""
    require_env_key("AQS_API_KEY")
    require_env_key("AQS_EMAIL")
    out = add_and_run(live_ws, "fetch.epa.aqs_annual", {
        "endpoint": "https://aqs.epa.gov/data/api/list/states",
    })
    assert_has_rows(out)


def test_live_epa_aqs_texas_ozone_jan_2024(live_ws):
    """Texas daily ozone for Jan 1-7 2024 — daily resolution + different param."""
    require_env_key("AQS_API_KEY")
    require_env_key("AQS_EMAIL")
    out = add_and_run(live_ws, "fetch.epa.aqs_annual", {
        "endpoint": "https://aqs.epa.gov/data/api/dailyData/byState",
        "params": {
            "param": "44201",
            "bdate": "20240101",
            "edate": "20240107",
            "state": "48",
        },
    })
    assert_has_rows(out)


def test_live_epa_aqs_aqi_pollutants_class(live_ws):
    """List parameters in the AQI POLLUTANTS class."""
    require_env_key("AQS_API_KEY")
    require_env_key("AQS_EMAIL")
    out = add_and_run(live_ws, "fetch.epa.aqs_annual", {
        "endpoint": "https://aqs.epa.gov/data/api/list/parametersByClass",
        "params": {"pc": "AQI POLLUTANTS"},
    })
    assert_has_rows(out)


def test_live_airnow(live_ws):
    require_env_key("AIRNOW_API_KEY")
    out = add_and_run(live_ws, "fetch.airnow", {
        "params": {"zipCode": "10001", "distance": 25},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    row = out["rows"][0]
    assert "AQI" in row or "ParameterName" in row, f"Unexpected AirNow row: {row}"


def test_live_airnow_nyc_current(live_ws):
    """Current AQI in NYC by ZIP."""
    require_env_key("AIRNOW_API_KEY")
    out = add_and_run(live_ws, "fetch.airnow", {
        "endpoint": "https://www.airnowapi.org/aq/observation/zipCode/current/",
        "params": {
            "zipCode": "10001",
            "distance": 25,
            "format": "application/json",
        },
    })
    assert_has_rows(out)


def test_live_airnow_la_current_latlong(live_ws):
    """Current AQI near LA by lat/lon — different endpoint."""
    require_env_key("AIRNOW_API_KEY")
    out = add_and_run(live_ws, "fetch.airnow", {
        "endpoint": "https://www.airnowapi.org/aq/observation/latLong/current/",
        "params": {
            "latitude": 34.05,
            "longitude": -118.25,
            "distance": 25,
            "format": "application/json",
        },
    })
    assert_has_rows(out)


def test_live_airnow_sf_historical_2024_09(live_ws):
    """Historical SF AQI on Sept 1 2024 — date format YYYY-MM-DDT00-0000."""
    require_env_key("AIRNOW_API_KEY")
    out = add_and_run(live_ws, "fetch.airnow", {
        "endpoint": "https://www.airnowapi.org/aq/observation/zipCode/historical/",
        "params": {
            "zipCode": "94102",
            "date": "2024-09-01T00-0000",
            "distance": 25,
            "format": "application/json",
        },
    })
    assert_has_rows(out)


def test_live_airnow_chicago_forecast(live_ws):
    """Chicago AQI forecast — different family (forecast not observation)."""
    require_env_key("AIRNOW_API_KEY")
    out = add_and_run(live_ws, "fetch.airnow", {
        "endpoint": "https://www.airnowapi.org/aq/forecast/zipCode/",
        "params": {
            "zipCode": "60601",
            "distance": 25,
            "format": "application/json",
        },
    })
    assert_has_rows(out)


# ── DATA_GOV_API_KEY group ───────────────────────────────────────────────


def test_live_college_scorecard(live_ws):
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.college_scorecard.schools", {
        "params": {"school.name": "Harvard"},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_college_scorecard_california_4year(live_ws):
    """California 4-year schools — state + degree-level filter."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.college_scorecard.schools", {
        "params": {
            "school.state": "CA",
            "school.degrees_awarded.predominant": 3,
            "fields": "id,school.name,school.city,school.state,latest.cost.tuition.in_state",
            "per_page": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    states = {r.get("school.state") for r in rows if isinstance(r, dict)}
    assert states == {"CA"}, f"expected CA only, got {states}"


def test_live_college_scorecard_near_zip_02138(live_ws):
    """Schools within 10 miles of Cambridge, MA — geo proximity."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.college_scorecard.schools", {
        "params": {
            "_zip": "02138",
            "_distance": "10mi",
            "fields": "id,school.name,school.city,school.state,latest.student.size",
            "per_page": 25,
        },
    })
    assert_has_rows(out)


def test_live_college_scorecard_named_mit(live_ws):
    """Search by school name containing MIT."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.college_scorecard.schools", {
        "params": {
            "school.name": "MIT",
            "fields": "id,school.name,latest.admissions.admission_rate.overall",
        },
    })
    assert_has_rows(out)


def test_live_college_scorecard_largest_4year(live_ws):
    """Largest 4-year schools by enrollment — sort by student size."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.college_scorecard.schools", {
        "params": {
            "school.degrees_awarded.predominant": 3,
            "sort": "latest.student.size:desc",
            "fields": "id,school.name,latest.student.size",
            "per_page": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    sizes = [r.get("latest.student.size", 0) for r in rows if isinstance(r, dict)]
    valid = [s for s in sizes if s is not None]
    assert valid == sorted(valid, reverse=True), f"not sorted desc: {valid}"


def test_live_nrel_alt_fuel_stations(live_ws):
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.nrel.alt_fuel_stations", {
        "params": {"state": "CA", "limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_nrel_ev_charging_california(live_ws):
    """EV charging stations in California — fuel + state filter."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.nrel.alt_fuel_stations", {
        "endpoint": "https://developer.nrel.gov/api/alt-fuel-stations/v1.json",
        "params": {"fuel_type": "ELEC", "state": "CA", "limit": 25},
    })
    assert_has_rows(out)
    rows = out["rows"]
    fuels = {r.get("fuel_type_code") for r in rows if isinstance(r, dict)}
    assert fuels == {"ELEC"}, f"expected ELEC only, got {fuels}"


def test_live_nrel_hydrogen_stations_nationwide(live_ws):
    """All hydrogen fueling stations nationwide."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.nrel.alt_fuel_stations", {
        "endpoint": "https://developer.nrel.gov/api/alt-fuel-stations/v1.json",
        "params": {"fuel_type": "HY", "limit": 25},
    })
    assert_has_rows(out)


def test_live_nrel_ev_near_san_francisco(live_ws):
    """EV chargers near SF — lat/lon radius via /nearest.json (Vienna-class trap: old `location=zip` retired Feb 2025)."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.nrel.alt_fuel_stations", {
        "endpoint": "https://developer.nrel.gov/api/alt-fuel-stations/v1/nearest.json",
        "params": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "fuel_type": "ELEC",
            "radius": 5,
            "limit": 25,
        },
    })
    assert_has_rows(out)


def test_live_nrel_e85_texas(live_ws):
    """E85 ethanol stations in Texas."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.nrel.alt_fuel_stations", {
        "endpoint": "https://developer.nrel.gov/api/alt-fuel-stations/v1.json",
        "params": {"fuel_type": "E85", "state": "TX", "limit": 25},
    })
    assert_has_rows(out)


def test_live_usda_fooddata_search(live_ws):
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.fooddata_search", {
        "params": {"query": "apple", "pageSize": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_usda_fooddata_search_apple(live_ws):
    """Foods matching 'apple'."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.fooddata_search", {
        "endpoint": "https://api.nal.usda.gov/fdc/v1/foods/search",
        "params": {"query": "apple", "pageSize": 25},
    })
    assert_has_rows(out)


def test_live_usda_fooddata_salmon_foundation(live_ws):
    """Salmon foods, restricted to Foundation+SR Legacy data types."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.fooddata_search", {
        "endpoint": "https://api.nal.usda.gov/fdc/v1/foods/search",
        "params": {
            "query": "salmon",
            "dataType": "Foundation,SR Legacy",
            "pageSize": 25,
        },
    })
    assert_has_rows(out)


def test_live_usda_fooddata_foods_list(live_ws):
    """Foods catalog browse — different endpoint."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.fooddata_search", {
        "endpoint": "https://api.nal.usda.gov/fdc/v1/foods/list",
        "params": {"pageSize": 25},
    })
    assert_has_rows(out)


def test_live_usda_fooddata_food_detail_167512(live_ws):
    """Detailed nutrient + portion data for fdcId 167512."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.usda.fooddata_search", {
        "endpoint": "https://api.nal.usda.gov/fdc/v1/food/167512",
    })
    # Single-food endpoint returns a top-level food object, not a list.
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    raw = out.get("raw")
    assert isinstance(raw, dict) and raw.get("fdcId") == 167512, f"expected fdcId 167512, got {raw.get('fdcId') if isinstance(raw, dict) else type(raw).__name__}"


def test_live_regulations_dockets(live_ws):
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.regulations.dockets")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_regulations_dockets_epa_dockets(live_ws):
    """EPA dockets — agency filter."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.regulations.dockets", {
        "endpoint": "https://api.regulations.gov/v4/dockets",
        "params": {"filter[agencyId]": "EPA", "page[size]": 25},
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Each docket attribute should have agencyId=EPA.
    agencies = {r.get("attributes", {}).get("agencyId") for r in rows if isinstance(r, dict)}
    assert agencies == {"EPA"}, f"expected EPA-only, got {agencies}"


def test_live_regulations_dockets_electric_vehicle_documents(live_ws):
    """Documents matching 'electric vehicle' full-text — different endpoint."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.regulations.dockets", {
        "endpoint": "https://api.regulations.gov/v4/documents",
        "params": {"filter[searchTerm]": "electric vehicle", "page[size]": 10},
    })
    assert_has_rows(out)


def test_live_regulations_dockets_recent_comments(live_ws):
    """Comments since Oct 1 2024 — date filter (full datetime format)."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.regulations.dockets", {
        "endpoint": "https://api.regulations.gov/v4/comments",
        "params": {
            "filter[lastModifiedDate][ge]": "2024-10-01 00:00:00",
            "page[size]": 25,
        },
    })
    assert_has_rows(out)


def test_live_regulations_dockets_climate_search(live_ws):
    """Dockets matching 'climate'."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.regulations.dockets", {
        "endpoint": "https://api.regulations.gov/v4/dockets",
        "params": {"filter[searchTerm]": "climate", "page[size]": 25},
    })
    assert_has_rows(out)


def test_live_fbi_crime(live_ws):
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fbi.crime")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_fbi_crime_california_arrests(live_ws):
    """California arrest counts 2020-2022 — state-level all-offense aggregate."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fbi.crime", {
        "endpoint": "https://api.usa.gov/crime/fbi/cde/arrest/state/CA/all",
        "params": {"type": "counts", "from": "01-2020", "to": "12-2022"},
    })
    assert_has_rows(out)


def test_live_fbi_crime_national_arrests(live_ws):
    """National arrest totals 2020-2022."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fbi.crime", {
        "endpoint": "https://api.usa.gov/crime/fbi/cde/arrest/national/all",
        "params": {"type": "counts", "from": "01-2020", "to": "12-2022"},
    })
    assert_has_rows(out)


def test_live_fbi_crime_ny_violent_crime_2022(live_ws):
    """New York violent crime summary for 2022 — hyphenated offense slug."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fbi.crime", {
        "endpoint": "https://api.usa.gov/crime/fbi/cde/summarized/state/NY/violent-crime",
        "params": {"from": "01-2022", "to": "12-2022"},
    })
    assert_has_rows(out)


def test_live_fbi_crime_national_aggravated_assault_2022(live_ws):
    """National aggravated-assault summary for 2022."""
    require_env_key("DATA_GOV_API_KEY")
    out = add_and_run(live_ws, "fetch.fbi.crime", {
        "endpoint": "https://api.usa.gov/crime/fbi/cde/summarized/national/aggravated-assault",
        "params": {"from": "01-2022", "to": "12-2022"},
    })
    assert_has_rows(out)


# ── DOL / USPTO ──────────────────────────────────────────────────────────


def test_live_dol_osha_inspections(live_ws):
    require_env_key("DOL_API_KEY")
    out = add_and_run(live_ws, "fetch.dol.osha_inspections", {
        "params": {"limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    # OSHA inspection rows have an activity_nr identifier.
    assert any("activity_nr" in r for r in out["rows"]), (
        f"expected activity_nr in OSHA inspection rows, got keys: "
        f"{list(out['rows'][0].keys())[:10] if out['rows'] else 'empty'}"
    )


def test_live_dol_osha_violations(live_ws):
    require_env_key("DOL_API_KEY")
    out = add_and_run(live_ws, "fetch.dol.osha_inspections", {
        "endpoint": "https://apiprod.dol.gov/v4/get/OSHA/violation/json",
        "params": {"limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_dol_msha_accidents(live_ws):
    require_env_key("DOL_API_KEY")
    out = add_and_run(live_ws, "fetch.dol.osha_inspections", {
        "endpoint": "https://apiprod.dol.gov/v4/get/MSHA/accident/json",
        "params": {"limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_dol_catalog_listing(live_ws):
    # /v4/datasets is the catalog and requires no API key.
    out = add_and_run(live_ws, "fetch.dol.osha_inspections", {
        "endpoint": "https://apiprod.dol.gov/v4/datasets",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    # Catalog rows are dataset descriptors with a name field.
    assert any("name" in r for r in out["rows"]), (
        "expected DOL catalog rows to have a 'name' field"
    )


def test_live_uspto_application(live_ws):
    require_env_key("USPTO_API_KEY")
    out = add_and_run(live_ws, "fetch.uspto.application")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_uspto_search(live_ws):
    require_env_key("USPTO_API_KEY")
    out = add_and_run(live_ws, "fetch.uspto.application", {
        "endpoint": "https://api.uspto.gov/api/v1/patent/applications/search",
        "method": "GET",
        "params": {"q": "solar", "limit": 10},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_uspto_continuity(live_ws):
    require_env_key("USPTO_API_KEY")
    out = add_and_run(live_ws, "fetch.uspto.application", {
        "endpoint": "https://api.uspto.gov/api/v1/patent/applications/17908782/continuity",
        "method": "GET",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    # Continuity bags may be empty for some apps — accept any valid response shape.
    assert isinstance(out["rows"], list)


def test_live_uspto_bulk_products(live_ws):
    require_env_key("USPTO_API_KEY")
    out = add_and_run(live_ws, "fetch.uspto.application", {
        "endpoint": "https://api.uspto.gov/api/v1/datasets/products/search",
        "method": "GET",
        "params": {"limit": 10},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
