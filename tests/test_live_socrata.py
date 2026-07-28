"""Live integration tests for Socrata-based modules.

These work without API keys but benefit from SODA_API_KEY_ID for higher rate limits.
Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_socrata.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _live_helpers import (
    add_and_run,
    assert_has_rows,
    assert_output_shape,
    assert_raw_saved,
    init_workspace,
    require_live_gate,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_live_gate()
    tmp = tmp_path_factory.mktemp("live_socrata")
    ws = init_workspace(tmp)
    return ws


# ── Large-tier Socrata (catalog-driven run.py) ───────────────────────────


def test_live_nyc_open_data(live_ws):
    # Use `eabe-havv` (Civic Engagement Commission voter registration counts) instead
    # of the massive 311 dataset (erm2-nwe9) which intermittently times out at 20s.
    # eabe-havv is a small lookup table, responds in <1s.
    out = add_and_run(live_ws, "fetch.nyc_open_data", {
        "base": "nyc_v2",
        "method": "GET",
        "path": "/resource/eabe-havv.json",
        "params": {"$limit": 5},
    })
    assert_output_shape(out, "provider", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.nyc_open_data")


def test_live_nyc_311_manhattan(live_ws):
    """NYC 311 service requests in Manhattan."""
    out = add_and_run(live_ws, "fetch.nyc_open_data", {
        "base": "nyc_v2",
        "method": "GET",
        "path": "/resource/erm2-nwe9.json",
        "params": {"$where": "borough='MANHATTAN'", "$limit": 25},
    })
    assert_has_rows(out)


def test_live_nyc_nypd_complaints_recent(live_ws):
    """Recent NYPD complaint data — different dataset."""
    out = add_and_run(live_ws, "fetch.nyc_open_data", {
        "base": "nyc_v2",
        "method": "GET",
        "path": "/resource/h9gi-nx95.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)


def test_live_nyc_views_catalog(live_ws):
    """List NYC Open Data views — metadata catalog."""
    out = add_and_run(live_ws, "fetch.nyc_open_data", {
        "base": "nyc",
        "method": "GET",
        "path": "/api/views.json",
        "params": {"limit": 25},
    })
    assert_has_rows(out)


def test_live_nyc_discovery_search(live_ws):
    """Cross-domain Socrata discovery for NYC datasets."""
    out = add_and_run(live_ws, "fetch.nyc_open_data", {
        "base": "catalog_v1",
        "method": "GET",
        "path": "/api/catalog/v1",
        "params": {"domains": "data.cityofnewyork.us", "limit": 25},
    })
    assert_has_rows(out)


def test_live_cdc(live_ws):
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/bi63-dtpu.json",
        "params": {"$limit": 5},
    })
    assert_output_shape(out, "provider", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.cdc")


def test_live_cdc_leading_causes_of_death_2017(live_ws):
    """Top causes of death in the US in 2017 — exercises $where + $order + $limit."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/bi63-dtpu.json",
        "params": {
            "$where": "year=2017 AND state='United States'",
            "$order": "deaths DESC",
            "$limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Heart Disease / Cancer should top the list.
    causes = [r.get("cause_name", "") for r in rows if isinstance(r, dict)]
    assert any("Heart" in c or "Cancer" in c for c in causes), (
        f"expected Heart/Cancer in top causes, got {causes[:5]}"
    )


def test_live_cdc_life_expectancy_2018(live_ws):
    """National life expectancy in 2018 by race/sex — single-year filter."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/w9j2-ggv5.json",
        "params": {
            "$where": "year='2018'",
            "$limit": 50,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    years = {r.get("year") for r in rows if isinstance(r, dict)}
    assert years == {"2018"}, f"expected only 2018, got years {years}"
    assert any(
        r.get("race") and r.get("sex") and r.get("average_life_expectancy")
        for r in rows if isinstance(r, dict)
    ), "expected race/sex/average_life_expectancy fields"


def test_live_cdc_places_county_obesity_cook_il(live_ws):
    """Adult obesity prevalence in Cook County, IL — multi-field filter."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/swc5-untb.json",
        "params": {
            "$where": "stateabbr='IL' AND locationname='Cook' AND measureid='OBESITY'",
            "$limit": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    assert all(
        r.get("stateabbr") == "IL" and r.get("locationname") == "Cook"
        for r in rows if isinstance(r, dict)
    ), f"expected all rows in IL/Cook, got {[(r.get('stateabbr'), r.get('locationname')) for r in rows[:3]]}"


def test_live_cdc_covid_cases_california_latest(live_ws):
    """Most recent weekly COVID-19 case totals in California — sort + state filter."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/pwn4-m3yp.json",
        "params": {
            "$where": "state='CA'",
            "$order": "end_date DESC",
            "$limit": 5,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    assert all(r.get("state") == "CA" for r in rows if isinstance(r, dict)), (
        f"expected all CA rows, got states {[r.get('state') for r in rows[:3]]}"
    )


def test_live_cdc_places_county_2024_obesity_il(live_ws):
    """PLACES 2024 release — adult obesity prevalence in Illinois counties (P1 health)."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/fu4u-a9bh.json",
        "params": {"stateabbr": "IL", "measureid": "OBESITY", "$limit": 25},
    })
    assert_has_rows(out)
    rows = out["rows"]
    assert all(r.get("stateabbr") == "IL" for r in rows if isinstance(r, dict)), (
        f"expected all IL rows, got states {[r.get('stateabbr') for r in rows[:3]]}"
    )
    assert all(
        r.get("measureid") == "OBESITY" for r in rows if isinstance(r, dict)
    ), "expected all OBESITY rows"


def test_live_cdc_nwss_wastewater_covid(live_ws):
    """NWSS Wastewater Monitoring — SARS-CoV-2 wastewater concentrations (P1 health)."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/j9g8-acpt.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # NWSS rows must have a sampling site and a state/territory.
    assert "site" in sample or "key_plot_id" in sample, (
        f"expected NWSS site identifier, got keys {list(sample.keys())[:8]}"
    )
    assert "state" in sample or "state_territory" in sample, (
        f"expected NWSS state/territory, got keys {list(sample.keys())[:8]}"
    )


def test_live_cdc_nwss_combined_pathogens(live_ws):
    """NWSS combined SARS-CoV-2 / Influenza A / RSV viral activity (P1 health)."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/atcp-73re.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)


def test_live_cdc_nvss_infant_mortality(live_ws):
    """NVSS infant, neonatal, postneonatal mortality rates by race (P1 health)."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/j7ym-uwqy.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # NVSS DQS infant mortality rows expose topic + classification.
    assert "topic" in sample, (
        f"expected NVSS topic, got keys {list(sample.keys())[:8]}"
    )
    assert "infant" in (sample.get("topic") or "").lower(), (
        f"expected infant mortality topic, got {sample.get('topic')!r}"
    )


def test_live_cdc_nvss_low_birthweight(live_ws):
    """NVSS low birthweight live births by state (P1 health)."""
    out = add_and_run(live_ws, "fetch.cdc", {
        "base": "resource",
        "method": "GET",
        "path": "/ga7k-kycn.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    assert "low birthweight" in (sample.get("topic") or "").lower(), (
        f"expected low birthweight topic, got {sample.get('topic')!r}"
    )


# ── Small-tier Socrata modules ───────────────────────────────────────────


def test_live_socrata_dataset(live_ws):
    out = add_and_run(live_ws, "fetch.socrata.dataset", {
        "domain": "data.seattle.gov",
        "dataset_id": "kzjm-xkqj",
        "limit": 5,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_socrata_dataset_seattle_911_calls_recent(live_ws):
    """Seattle 911 calls sorted by datetime DESC — exercises params $order pass-through."""
    out = add_and_run(live_ws, "fetch.socrata.dataset", {
        "domain": "data.seattle.gov",
        "dataset_id": "kzjm-xkqj",
        "limit": 50,
        "params": {"$order": "datetime DESC"},
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Datetimes should be in descending order.
    times = [r.get("datetime") for r in rows if isinstance(r, dict) and r.get("datetime")]
    assert times == sorted(times, reverse=True), (
        f"expected descending order, got {times[:3]}"
    )


def test_live_socrata_dataset_nyc_311_complaints_by_borough(live_ws):
    """NYC 311 — group by complaint_type with count, filter by Manhattan."""
    out = add_and_run(live_ws, "fetch.socrata.dataset", {
        "domain": "data.cityofnewyork.us",
        "dataset_id": "erm2-nwe9",
        "limit": 10,
        "where": "borough='MANHATTAN'",
        "params": {
            "$select": "complaint_type, count(*) as count",
            "$group": "complaint_type",
            "$order": "count DESC",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Each row should have complaint_type and count (aggregated).
    assert all(
        r.get("complaint_type") and r.get("count")
        for r in rows if isinstance(r, dict)
    ), f"expected complaint_type/count rows, got {rows[:2]}"


def test_live_socrata_dataset_chicago_crimes_2024(live_ws):
    """Chicago crimes in 2024 — date range filter."""
    out = add_and_run(live_ws, "fetch.socrata.dataset", {
        "domain": "data.cityofchicago.org",
        "dataset_id": "ijzp-q8t2",
        "limit": 25,
        "where": "date between '2024-01-01T00:00:00' and '2024-12-31T23:59:59'",
        "params": {"$order": "date DESC"},
    })
    assert_has_rows(out)
    rows = out["rows"]
    dates = [r.get("date", "")[:4] for r in rows if isinstance(r, dict)]
    assert all(d == "2024" for d in dates), f"expected only 2024 dates, got {set(dates)}"


def test_live_socrata_dataset_full_text_search_noise(live_ws):
    """Full-text search 'noise' in NYC 311 complaints — exercises $q."""
    out = add_and_run(live_ws, "fetch.socrata.dataset", {
        "domain": "data.cityofnewyork.us",
        "dataset_id": "erm2-nwe9",
        "limit": 10,
        "params": {"$q": "noise"},
    })
    assert_has_rows(out)


def test_live_socrata_chicago_crimes(live_ws):
    out = add_and_run(live_ws, "fetch.socrata.chicago_crimes", {
        "params": {"$limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_socrata_chicago_latest(live_ws):
    """Most recent Chicago crimes — sort by date desc."""
    out = add_and_run(live_ws, "fetch.socrata.chicago_crimes", {
        "endpoint": "https://data.cityofchicago.org/resource/ijzp-q8t2.json",
        "params": {"$order": "date DESC", "$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_chicago_2024(live_ws):
    """Chicago crimes in 2024 — year filter."""
    out = add_and_run(live_ws, "fetch.socrata.chicago_crimes", {
        "endpoint": "https://data.cityofchicago.org/resource/ijzp-q8t2.json",
        "params": {"$where": "year=2024", "$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_chicago_top_types(live_ws):
    """Top crime types by count — aggregation."""
    out = add_and_run(live_ws, "fetch.socrata.chicago_crimes", {
        "endpoint": "https://data.cityofchicago.org/resource/ijzp-q8t2.json",
        "params": {
            "$select": "primary_type, count(*) as count",
            "$group": "primary_type",
            "$order": "count DESC",
            "$limit": 10,
        },
    })
    assert_has_rows(out)


def test_live_socrata_chicago_different_dataset(live_ws):
    """Different Chicago dataset (CTA/transit data) on same domain."""
    out = add_and_run(live_ws, "fetch.socrata.chicago_crimes", {
        "endpoint": "https://data.cityofchicago.org/resource/x2n5-8w5q.json",
        "params": {"$limit": 5},
    })
    assert_has_rows(out)


def test_live_socrata_la_crime(live_ws):
    out = add_and_run(live_ws, "fetch.socrata.la_crime", {
        "params": {"$limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_socrata_la_latest(live_ws):
    """Most recent LAPD crime reports."""
    out = add_and_run(live_ws, "fetch.socrata.la_crime", {
        "endpoint": "https://data.lacity.org/resource/2nrs-mtv8.json",
        "params": {"$order": "date_rptd DESC", "$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_la_top_descriptions(live_ws):
    """Top crime descriptions by count."""
    out = add_and_run(live_ws, "fetch.socrata.la_crime", {
        "endpoint": "https://data.lacity.org/resource/2nrs-mtv8.json",
        "params": {
            "$select": "crm_cd_desc, count(*) as count",
            "$group": "crm_cd_desc",
            "$order": "count DESC",
            "$limit": 10,
        },
    })
    assert_has_rows(out)


def test_live_socrata_la_2024(live_ws):
    """LAPD crimes reported in 2024."""
    out = add_and_run(live_ws, "fetch.socrata.la_crime", {
        "endpoint": "https://data.lacity.org/resource/2nrs-mtv8.json",
        "params": {
            "$where": "date_rptd >= '2024-01-01T00:00:00' AND date_rptd < '2025-01-01T00:00:00'",
            "$limit": 25,
        },
    })
    assert_has_rows(out)


def test_live_socrata_la_traffic_collisions(live_ws):
    """LA Traffic Collisions — different dataset on same domain."""
    out = add_and_run(live_ws, "fetch.socrata.la_crime", {
        "endpoint": "https://data.lacity.org/resource/d5tf-ez2w.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_sf_building_permits(live_ws):
    out = add_and_run(live_ws, "fetch.socrata.sf_building_permits", {
        "params": {"$limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_socrata_sf_latest_permits(live_ws):
    """Most recent SF permits."""
    out = add_and_run(live_ws, "fetch.socrata.sf_building_permits", {
        "endpoint": "https://data.sfgov.org/resource/i98e-djp9.json",
        "params": {"$order": "filed_date DESC", "$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_sf_permits_by_type(live_ws):
    """Top SF permit types (aggregation)."""
    out = add_and_run(live_ws, "fetch.socrata.sf_building_permits", {
        "endpoint": "https://data.sfgov.org/resource/i98e-djp9.json",
        "params": {
            "$select": "permit_type_definition, count(*) as count",
            "$group": "permit_type_definition",
            "$order": "count DESC",
            "$limit": 10,
        },
    })
    assert_has_rows(out)


def test_live_socrata_sf_permits_2024(live_ws):
    """SF permits filed in 2024."""
    out = add_and_run(live_ws, "fetch.socrata.sf_building_permits", {
        "endpoint": "https://data.sfgov.org/resource/i98e-djp9.json",
        "params": {
            "$where": "filed_date >= '2024-01-01T00:00:00' AND filed_date < '2025-01-01T00:00:00'",
            "$limit": 25,
        },
    })
    assert_has_rows(out)


def test_live_socrata_sf_parking_dataset(live_ws):
    """SF parking dataset — different dataset on same domain."""
    out = add_and_run(live_ws, "fetch.socrata.sf_building_permits", {
        "endpoint": "https://data.sfgov.org/resource/wr8u-xric.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_seattle_building_permits(live_ws):
    out = add_and_run(live_ws, "fetch.socrata.seattle_building_permits", {
        "params": {"$limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_socrata_seattle_latest(live_ws):
    """Most recent Seattle permits."""
    out = add_and_run(live_ws, "fetch.socrata.seattle_building_permits", {
        "endpoint": "https://data.seattle.gov/resource/76t5-zqzr.json",
        "params": {"$order": "issueddate DESC", "$limit": 25},
    })
    assert_has_rows(out)


def test_live_socrata_seattle_by_class(live_ws):
    """Top Seattle permit classes (aggregation)."""
    out = add_and_run(live_ws, "fetch.socrata.seattle_building_permits", {
        "endpoint": "https://data.seattle.gov/resource/76t5-zqzr.json",
        "params": {
            "$select": "permitclass, count(*) as count",
            "$group": "permitclass",
            "$order": "count DESC",
            "$limit": 10,
        },
    })
    assert_has_rows(out)


def test_live_socrata_seattle_2024(live_ws):
    """Seattle permits issued in 2024."""
    out = add_and_run(live_ws, "fetch.socrata.seattle_building_permits", {
        "endpoint": "https://data.seattle.gov/resource/76t5-zqzr.json",
        "params": {
            "$where": "issueddate >= '2024-01-01T00:00:00' AND issueddate < '2025-01-01T00:00:00'",
            "$limit": 25,
        },
    })
    assert_has_rows(out)


def test_live_socrata_seattle_land_use(live_ws):
    """Seattle Land Use dataset — different dataset on same domain."""
    out = add_and_run(live_ws, "fetch.socrata.seattle_building_permits", {
        "endpoint": "https://data.seattle.gov/resource/4xy5-26gy.json",
        "params": {"$limit": 25},
    })
    assert_has_rows(out)
