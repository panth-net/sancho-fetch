"""Live integration tests for modules that require NO API key.

Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_nokey.py -v
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
    require_live_gate,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_live_gate()
    tmp = tmp_path_factory.mktemp("live_nokey")
    ws = init_workspace(tmp)
    return ws


# ── US Federal (no key) ──────────────────────────────────────────────────


def test_live_usgs_earthquakes(live_ws):
    out = add_and_run(live_ws, "fetch.usgs.earthquakes", {
        "params": {"format": "geojson", "limit": 5, "orderby": "time"},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert out["dataset_ref"] == "usgov_usgs"
    assert_has_rows(out)
    # USGS GeoJSON features have id + properties
    first = out["rows"][0]
    assert "id" in first or "properties" in first


def test_live_usgs_earthquakes_large_quakes_january_2024(live_ws):
    """Magnitude 5+ earthquakes in the first week of 2024."""
    out = add_and_run(live_ws, "fetch.usgs.earthquakes", {
        "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
        "params": {
            "format": "geojson",
            "starttime": "2024-01-01",
            "endtime": "2024-01-07",
            "minmagnitude": 5,
            "limit": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    mags = [r.get("properties", {}).get("mag") for r in rows if isinstance(r, dict)]
    assert all(m is None or m >= 5 for m in mags), f"expected M5+, got {mags[:5]}"


def test_live_usgs_earthquakes_california_january_2024(live_ws):
    """California-bbox earthquakes in January 2024 (M4+)."""
    out = add_and_run(live_ws, "fetch.usgs.earthquakes", {
        "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
        "params": {
            "format": "geojson",
            "starttime": "2024-01-01",
            "endtime": "2024-01-31",
            "minlatitude": 32, "maxlatitude": 42,
            "minlongitude": -125, "maxlongitude": -114,
            "minmagnitude": 4,
            "limit": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Each event's longitude should be in California bbox.
    coords = [r.get("geometry", {}).get("coordinates", []) for r in rows if isinstance(r, dict)]
    valid = [c for c in coords if isinstance(c, list) and len(c) >= 2]
    assert all(-125 <= c[0] <= -114 and 32 <= c[1] <= 42 for c in valid), (
        f"events outside CA bbox: {[(c[1], c[0]) for c in valid[:3]]}"
    )


def test_live_usgs_earthquakes_largest_january_2024(live_ws):
    """Top 5 largest earthquakes in January 2024 (sort by magnitude)."""
    out = add_and_run(live_ws, "fetch.usgs.earthquakes", {
        "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
        "params": {
            "format": "geojson",
            "starttime": "2024-01-01",
            "endtime": "2024-01-31",
            "orderby": "magnitude",
            "limit": 5,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    mags = [r.get("properties", {}).get("mag", 0) for r in rows if isinstance(r, dict)]
    # Should be sorted descending.
    valid = [m for m in mags if m is not None]
    assert valid == sorted(valid, reverse=True), f"not sorted desc: {valid}"


def test_live_usgs_earthquakes_noto_peninsula_2024(live_ws):
    """The 2024 Noto Peninsula M7.5 earthquake by event ID."""
    out = add_and_run(live_ws, "fetch.usgs.earthquakes", {
        "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
        "params": {"format": "geojson", "eventid": "us6000m0xl"},
    })
    assert_has_rows(out)
    rows = out["rows"]
    # The single event response is a Feature, not a FeatureCollection — it
    # gets wrapped in `features` by the wrapper.
    found = any(
        "Noto" in (r.get("properties", {}).get("place", "") or "")
        for r in rows if isinstance(r, dict)
    )
    assert found, f"expected Noto Peninsula, got {[r.get('properties', {}).get('place') for r in rows[:3]]}"


def test_live_treasury_fiscal_data(live_ws):
    out = add_and_run(live_ws, "fetch.treasury.fiscal_data", {
        "params": {"page[size]": "5"},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert out["dataset_ref"] == "usgov_treasury_fiscal"
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.treasury.fiscal_data")


def test_live_treasury_fiscal_rates_of_exchange_2024(live_ws):
    """Rates of exchange since Jan 2024 — date filter + sort."""
    out = add_and_run(live_ws, "fetch.treasury.fiscal_data", {
        "endpoint": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange",
        "params": {
            "filter": "record_date:gte:2024-01-01",
            "page[size]": 25,
            "sort": "-record_date",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    dates = [r.get("record_date") for r in rows if isinstance(r, dict)]
    assert all(d >= "2024-01-01" for d in dates if d), f"expected dates >= 2024-01-01, got {dates[:3]}"


def test_live_treasury_fiscal_debt_to_penny_recent(live_ws):
    """Most recent daily public debt — different endpoint."""
    out = add_and_run(live_ws, "fetch.treasury.fiscal_data", {
        "endpoint": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
        "params": {"sort": "-record_date", "page[size]": 10},
    })
    assert_has_rows(out)


def test_live_treasury_fiscal_avg_interest_rates_2024(live_ws):
    """Average Treasury interest rates since 2024."""
    out = add_and_run(live_ws, "fetch.treasury.fiscal_data", {
        "endpoint": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates",
        "params": {
            "filter": "record_date:gte:2024-01-01",
            "sort": "-record_date",
            "page[size]": 25,
        },
    })
    assert_has_rows(out)


def test_live_treasury_fiscal_securities_sales_recent(live_ws):
    """Recent Treasury securities issuance — different dataset."""
    out = add_and_run(live_ws, "fetch.treasury.fiscal_data", {
        "endpoint": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/securities_sales",
        "params": {"sort": "-record_date", "page[size]": 10},
    })
    assert_has_rows(out)


def test_live_cfpb_complaints(live_ws):
    out = add_and_run(live_ws, "fetch.cfpb.complaints", {
        "params": {"size": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_cfpb_complaints_mortgage_recent(live_ws):
    """Recent mortgage complaints — product filter + sort."""
    out = add_and_run(live_ws, "fetch.cfpb.complaints", {
        "params": {
            "product": "Mortgage",
            "size": 25,
            "sort": "created_date_desc",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    products = {r.get("product") for r in rows if isinstance(r, dict)}
    assert products == {"Mortgage"}, f"expected Mortgage only, got {products}"


def test_live_cfpb_complaints_california_january_2024(live_ws):
    """California complaints from January 2024 — state + date range."""
    out = add_and_run(live_ws, "fetch.cfpb.complaints", {
        "params": {
            "state": "CA",
            "date_received_min": "2024-01-01",
            "date_received_max": "2024-01-31",
            "size": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    states = {r.get("state") for r in rows if isinstance(r, dict)}
    assert states == {"CA"}, f"expected CA only, got {states}"


def test_live_cfpb_complaints_wells_fargo(live_ws):
    """Wells Fargo complaints — exact company name (Vienna-class trap)."""
    out = add_and_run(live_ws, "fetch.cfpb.complaints", {
        "params": {
            "company": "WELLS FARGO & COMPANY",
            "size": 25,
            "sort": "created_date_desc",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    companies = {r.get("company") for r in rows if isinstance(r, dict)}
    assert companies == {"WELLS FARGO & COMPANY"}, f"expected Wells Fargo, got {companies}"


def test_live_cfpb_complaints_student_loan_narrative(live_ws):
    """Student loan complaints with consumer narrative — full-text + filter."""
    out = add_and_run(live_ws, "fetch.cfpb.complaints", {
        "params": {
            "has_narrative": "true",
            "search_term": "student loan",
            "size": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # All should have a consumer narrative.
    narratives = [r.get("complaint_what_happened") for r in rows if isinstance(r, dict)]
    assert all(n for n in narratives), f"expected all rows with narratives"


def test_live_clinical_trials(live_ws):
    out = add_and_run(live_ws, "fetch.clinical_trials.studies", {
        "endpoint": "https://clinicaltrials.gov/api/v2/studies",
        "params": {"query.term": "diabetes", "pageSize": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_clinical_trials_recruiting_diabetes_socal(live_ws):
    """Recruiting diabetes trials within 200mi of LA — geo + status filter."""
    out = add_and_run(live_ws, "fetch.clinical_trials.studies", {
        "endpoint": "https://clinicaltrials.gov/api/v2/studies",
        "params": {
            "query.cond": "diabetes",
            "filter.geo": "distance(34.05,-118.25,200mi)",
            "filter.overallStatus": "RECRUITING",
            "pageSize": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # All studies should have RECRUITING status.
    for row in rows[:3]:
        if isinstance(row, dict):
            status = row.get("protocolSection", {}).get("statusModule", {}).get("overallStatus")
            assert status == "RECRUITING", f"expected RECRUITING, got {status}"


def test_live_clinical_trials_recent_recruiting_cancer(live_ws):
    """Recruiting cancer trials sorted by most recently updated."""
    out = add_and_run(live_ws, "fetch.clinical_trials.studies", {
        "endpoint": "https://clinicaltrials.gov/api/v2/studies",
        "params": {
            "query.cond": "cancer",
            "filter.overallStatus": "RECRUITING",
            "sort": "LastUpdatePostDate:desc",
            "pageSize": 10,
        },
    })
    assert_has_rows(out)


def test_live_clinical_trials_single_study_by_nct_id(live_ws):
    """Fetch a specific trial by NCT identifier — different response shape."""
    out = add_and_run(live_ws, "fetch.clinical_trials.studies", {
        "endpoint": "https://clinicaltrials.gov/api/v2/studies/NCT04308668",
    })
    # Single-study endpoint wraps `protocolSection` directly. The transform
    # may surface this as `rows: [protocolSection]` or similar — assert keys.
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")


def test_live_clinical_trials_completed_covid_trials_count(live_ws):
    """Count of completed COVID-19 trials — exercises countTotal."""
    out = add_and_run(live_ws, "fetch.clinical_trials.studies", {
        "endpoint": "https://clinicaltrials.gov/api/v2/studies",
        "params": {
            "query.cond": "COVID-19",
            "filter.overallStatus": "COMPLETED",
            "countTotal": "true",
            "pageSize": 1,
        },
    })
    assert_has_rows(out)


def test_live_fdic_institutions(live_ws):
    out = add_and_run(live_ws, "fetch.fdic.institutions", {
        "endpoint": "https://banks.data.fdic.gov/api/institutions",
        "params": {"limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_fdic_institutions_california_banks(live_ws):
    """All FDIC banks in California — single-state filter."""
    out = add_and_run(live_ws, "fetch.fdic.institutions", {
        "endpoint": "https://banks.data.fdic.gov/api/institutions",
        "params": {
            "filters": 'STNAME:"California"',
            "fields": "NAME,STNAME,CITY,ASSET,ACTIVE",
            "limit": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    states = {r.get("data", {}).get("STNAME") for r in rows if isinstance(r, dict)}
    assert states == {"California"}, f"expected only California, got {states}"


def test_live_fdic_institutions_top_assets_active_banks(live_ws):
    """Largest active banks (>$10B) — range filter + boolean AND + sort."""
    out = add_and_run(live_ws, "fetch.fdic.institutions", {
        "endpoint": "https://banks.data.fdic.gov/api/institutions",
        "params": {
            "filters": "ASSET:[10000000 TO *] AND ACTIVE:1",
            "fields": "NAME,ASSET,CITY,STNAME",
            "sort_by": "ASSET",
            "sort_order": "DESC",
            "limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    assets = [r.get("data", {}).get("ASSET", 0) for r in rows if isinstance(r, dict)]
    # All should be >= 10000000 (in thousands of dollars).
    assert all(a >= 10000000 for a in assets), f"expected all >= 10M, got {assets[:5]}"
    # Should be sorted descending.
    assert assets == sorted(assets, reverse=True), f"not sorted desc: {assets}"


def test_live_fdic_institutions_houston_texas_branches(live_ws):
    """Bank branches in Houston, Texas — different endpoint (locations)."""
    out = add_and_run(live_ws, "fetch.fdic.institutions", {
        "endpoint": "https://banks.data.fdic.gov/api/locations",
        "params": {
            "filters": 'STNAME:"Texas" AND CITY:"Houston"',
            "fields": "NAME,ADDRESS,CITY,STNAME",
            "limit": 25,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    cities = {r.get("data", {}).get("CITY") for r in rows if isinstance(r, dict)}
    assert cities == {"Houston"}, f"expected only Houston, got {cities}"


def test_live_fdic_institutions_jpmorgan_chase_financials(live_ws):
    """JPMorgan Chase historical quarterly financials — financials endpoint."""
    out = add_and_run(live_ws, "fetch.fdic.institutions", {
        "endpoint": "https://banks.data.fdic.gov/api/financials",
        "params": {
            "filters": "CERT:3511",
            "fields": "CERT,REPDTE,ASSET,DEP",
            "limit": 10,
            "sort_by": "REPDTE",
            "sort_order": "DESC",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    certs = {r.get("data", {}).get("CERT") for r in rows if isinstance(r, dict)}
    assert certs == {3511}, f"expected only CERT 3511, got {certs}"


def test_live_fema_openfema(live_ws):
    out = add_and_run(live_ws, "fetch.fema.openfema", {
        "endpoint": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
        "params": {"$top": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["disasterNumber"])


def test_live_fema_openfema_california_disasters_recent(live_ws):
    """California disaster declarations since 2023 — state + date filter."""
    out = add_and_run(live_ws, "fetch.fema.openfema", {
        "endpoint": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
        "params": {
            "$filter": "state eq 'CA' and declarationDate ge '2023-01-01'",
            "$top": 25,
            "$orderby": "declarationDate desc",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    states = {r.get("state") for r in rows if isinstance(r, dict)}
    assert states == {"CA"}, f"expected CA only, got {states}"


def test_live_fema_openfema_hurricanes_all(live_ws):
    """All hurricane disasters — incidentType filter."""
    out = add_and_run(live_ws, "fetch.fema.openfema", {
        "endpoint": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
        "params": {
            "$filter": "incidentType eq 'Hurricane'",
            "$top": 25,
            "$orderby": "declarationDate desc",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    types = {r.get("incidentType") for r in rows if isinstance(r, dict)}
    assert types == {"Hurricane"}, f"expected Hurricane only, got {types}"


def test_live_fema_openfema_latest_disasters(live_ws):
    """Most recent disaster declarations nationwide — sort + top."""
    out = add_and_run(live_ws, "fetch.fema.openfema", {
        "endpoint": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
        "params": {
            "$top": 25,
            "$orderby": "declarationDate desc",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    dates = [r.get("declarationDate") for r in rows if isinstance(r, dict)]
    valid = [d for d in dates if isinstance(d, str)]
    assert valid == sorted(valid, reverse=True), f"not sorted desc: {valid[:3]}"


def test_live_fema_openfema_web_disaster_summaries(live_ws):
    """FemaWebDisasterSummaries — different dataset."""
    out = add_and_run(live_ws, "fetch.fema.openfema", {
        "endpoint": "https://www.fema.gov/api/open/v1/FemaWebDisasterSummaries",
        "params": {"$top": 25, "$orderby": "disasterNumber desc"},
    })
    assert_has_rows(out)


def test_live_sec_company_submissions(live_ws):
    out = add_and_run(live_ws, "fetch.sec.company_submissions")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_sec_apple_submissions(live_ws):
    """Apple's filing index (CIK 320193)."""
    out = add_and_run(live_ws, "fetch.sec.company_submissions", {
        "endpoint": "https://data.sec.gov/submissions/CIK0000320193.json",
    })
    assert_has_rows(out)


def test_live_sec_apple_xbrl_company_facts(live_ws):
    """All XBRL financial concepts ever filed by Apple."""
    out = add_and_run(live_ws, "fetch.sec.company_submissions", {
        "endpoint": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
    })
    assert_has_rows(out)


def test_live_sec_apple_revenue_history(live_ws):
    """Apple's reported revenue across all filings — single concept time-series."""
    out = add_and_run(live_ws, "fetch.sec.company_submissions", {
        "endpoint": "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/Revenues.json",
    })
    assert_has_rows(out)


def test_live_sec_revenues_cy2023q1(live_ws):
    """Cross-company revenue snapshot for Q1 2023 — frames endpoint."""
    out = add_and_run(live_ws, "fetch.sec.company_submissions", {
        "endpoint": "https://data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY2023Q1I.json",
    })
    assert_has_rows(out)


def test_live_usaspending_awards(live_ws):
    out = add_and_run(live_ws, "fetch.usaspending.awards")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["Award ID"])


def test_live_usaspending_awards_top_lockheed_contracts_2024(live_ws):
    """Top Lockheed Martin contracts in 2024 — recipient filter + contract types."""
    out = add_and_run(live_ws, "fetch.usaspending.awards", {
        "endpoint": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        "params": {
            "filters": {
                "time_period": [{"start_date": "2024-01-01", "end_date": "2024-12-31"}],
                "award_type_codes": ["A", "B", "C", "D"],
                "recipient_search_text": ["LOCKHEED MARTIN"],
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
            "sort": "Award Amount",
            "order": "desc",
            "limit": 10,
            "page": 1,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    names = [r.get("Recipient Name", "") for r in rows if isinstance(r, dict)]
    assert any("LOCKHEED" in n.upper() for n in names), (
        f"expected LOCKHEED in recipient names, got {names[:3]}"
    )


def test_live_usaspending_awards_california_grants_2024(live_ws):
    """Grants in California in 2024 — geo + grant award type codes."""
    out = add_and_run(live_ws, "fetch.usaspending.awards", {
        "endpoint": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        "params": {
            "filters": {
                "time_period": [{"start_date": "2024-01-01", "end_date": "2024-12-31"}],
                "award_type_codes": ["02", "03", "04", "05"],
                "place_of_performance_locations": [{"country": "USA", "state": "CA"}],
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Place of Performance State Code"],
            "sort": "Award Amount",
            "order": "desc",
            "limit": 10,
            "page": 1,
        },
    })
    assert_has_rows(out)


def test_live_usaspending_awards_toptier_agencies(live_ws):
    """List of US federal toptier agencies — GET reference endpoint."""
    out = add_and_run(live_ws, "fetch.usaspending.awards", {
        "endpoint": "https://api.usaspending.gov/api/v2/references/toptier_agencies/",
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Should contain hundreds of toptier agencies — DOD, etc.
    names = [r.get("agency_name", "") for r in rows if isinstance(r, dict)]
    assert any("Defense" in n or "Treasury" in n for n in names), (
        f"expected Defense or Treasury in agency names, got {names[:5]}"
    )


def test_live_usaspending_awards_spending_by_category_agency_2024(live_ws):
    """Spending broken down by awarding agency in 2024 — aggregation endpoint."""
    out = add_and_run(live_ws, "fetch.usaspending.awards", {
        "endpoint": "https://api.usaspending.gov/api/v2/search/spending_by_category/awarding_agency/",
        "params": {
            "filters": {
                "time_period": [{"start_date": "2024-01-01", "end_date": "2024-12-31"}],
            },
            "category": "awarding_agency",
            "limit": 10,
            "page": 1,
        },
    })
    assert_has_rows(out)


def test_live_federal_register(live_ws):
    out = add_and_run(live_ws, "fetch.federal_register.documents", {
        "params": {"per_page": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_federal_register_documents_recent_proposed_rules(live_ws):
    """Recent proposed rules — type filter + date range."""
    out = add_and_run(live_ws, "fetch.federal_register.documents", {
        "endpoint": "https://www.federalregister.gov/api/v1/documents.json",
        "params": {
            "conditions[type][]": "PRORULE",
            "conditions[publication_date][gte]": "2024-10-01",
            "per_page": 25,
            "order": "newest",
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    types = {r.get("type") for r in rows if isinstance(r, dict)}
    assert types == {"Proposed Rule"}, f"expected Proposed Rule only, got {types}"


def test_live_federal_register_documents_climate_change_search(live_ws):
    """Full-text search 'climate change'."""
    out = add_and_run(live_ws, "fetch.federal_register.documents", {
        "endpoint": "https://www.federalregister.gov/api/v1/documents.json",
        "params": {
            "conditions[term]": "climate change",
            "per_page": 10,
            "order": "newest",
        },
    })
    assert_has_rows(out)


def test_live_federal_register_documents_epa_recent_documents(live_ws):
    """Recent EPA documents — agency slug filter."""
    out = add_and_run(live_ws, "fetch.federal_register.documents", {
        "endpoint": "https://www.federalregister.gov/api/v1/documents.json",
        "params": {
            "conditions[agencies][]": "environmental-protection-agency",
            "per_page": 10,
            "order": "newest",
        },
    })
    assert_has_rows(out)


def test_live_federal_register_documents_agencies_list(live_ws):
    """List of all Federal Register agencies."""
    out = add_and_run(live_ws, "fetch.federal_register.documents", {
        "endpoint": "https://www.federalregister.gov/api/v1/agencies.json",
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Should have 400+ agencies.
    assert len(rows) >= 100, f"expected >=100 agencies, got {len(rows)}"


def test_live_cms_data(live_ws):
    out = add_and_run(live_ws, "fetch.cms.data")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_cms_data_list_all_datasets(live_ws):
    """List all CMS provider-data datasets."""
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
        "params": {"limit": 25},
    })
    assert_has_rows(out)


def test_live_cms_data_dcat_catalog(live_ws):
    """DCAT-US catalog at /data.json."""
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/data.json",
    })
    assert_has_rows(out)


def test_live_cms_data_query_hospital_complications(live_ws):
    """Query Hospital General Information dataset rows."""
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0",
        "params": {"limit": 25},
    })
    assert_has_rows(out)


def test_live_cms_data_search_hospital(live_ws):
    """Full-text search 'hospital'."""
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/provider-data/api/1/search",
        "params": {"fulltext": "hospital"},
    })
    assert_has_rows(out)


def test_live_cms_data_fqhc_all_owners(live_ws):
    """Federally Qualified Health Center All Owners — health-data P0 source."""
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/data-api/v1/dataset/ed289c89-0bb8-4221-a20a-85776066381b/data",
        "params": {"size": 25},
    })
    assert_has_rows(out)
    # Each row must carry an enrollment id and an organization name (FQHC schema).
    sample = out["rows"][0]
    assert any(
        k in sample for k in ("ENROLLMENT ID", "ENROLLMENT_ID", "enrollment_id")
    ), f"FQHC row missing enrollment id, got keys: {list(sample.keys())[:8]}"


def test_live_cms_data_medicare_ffs_provider_enrollment(live_ws):
    """Medicare Fee-for-Service Public Provider Enrollment — health-data P0 source."""
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/data-api/v1/dataset/2457ea29-fc82-48b0-86ec-3b0755de7515/data",
        "params": {"size": 25},
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # FFS rows carry an NPI and provider type.
    assert "NPI" in sample, f"FFS row missing NPI, got keys: {list(sample.keys())[:8]}"


def test_live_cms_data_hcahps_metadata(live_ws):
    """HCAHPS hospital patient survey — metadata only (data is 100MB+ CSV).

    The HCAHPS Hospital dataset (dgck-syfz) is too large for live datastore
    queries; the canonical consumption path is the linked CSV download. Here
    we verify the metadata endpoint is reachable so the AI client can find
    the download URL.
    """
    out = add_and_run(live_ws, "fetch.cms.data", {
        "endpoint": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/dgck-syfz",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    raw = out.get("raw", {})
    assert "HCAHPS" in (raw.get("title") or ""), (
        f"expected HCAHPS metadata, got title={raw.get('title')!r}"
    )
    # Should expose a CSV download URL in distribution[*].downloadURL
    distributions = raw.get("distribution") or []
    download_urls = [
        d.get("downloadURL") or d.get("accessURL") for d in distributions
    ]
    assert any(u and "HCAHPS" in u for u in download_urls), (
        f"expected HCAHPS CSV download URL in distributions, got {download_urls}"
    )


def test_live_doj_press_releases(live_ws):
    out = add_and_run(live_ws, "fetch.doj.press_releases")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_doj_latest_press_releases(live_ws):
    """Most recent DOJ press releases — sort desc."""
    out = add_and_run(live_ws, "fetch.doj.press_releases", {
        "endpoint": "https://www.justice.gov/api/v1/press_releases.json",
        "params": {"pagesize": 25, "sort": "-date"},
    })
    assert_has_rows(out)


def test_live_doj_cybersecurity_search(live_ws):
    """Full-text search 'cybersecurity' in press releases."""
    out = add_and_run(live_ws, "fetch.doj.press_releases", {
        "endpoint": "https://www.justice.gov/api/v1/press_releases.json",
        "params": {"pagesize": 25, "q": "cybersecurity"},
    })
    assert_has_rows(out)


def test_live_doj_opa_press_releases(live_ws):
    """Office of Public Affairs press releases — component slug filter."""
    out = add_and_run(live_ws, "fetch.doj.press_releases", {
        "endpoint": "https://www.justice.gov/api/v1/press_releases.json",
        "params": {"pagesize": 25, "component": "opa", "sort": "-date"},
    })
    assert_has_rows(out)


def test_live_doj_latest_blog_entries(live_ws):
    """Most recent DOJ blog entries — different content type."""
    out = add_and_run(live_ws, "fetch.doj.press_releases", {
        "endpoint": "https://www.justice.gov/api/v1/blog_entries.json",
        "params": {"pagesize": 25, "sort": "-date"},
    })
    assert_has_rows(out)


def test_live_epa_echo_facilities(live_ws):
    out = add_and_run(live_ws, "fetch.epa.echo_facilities")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_epa_echo_cwa_virginia(live_ws):
    """CWA facilities in Virginia (cluster summary)."""
    out = add_and_run(live_ws, "fetch.epa.echo_facilities", {
        "endpoint": "https://echodata.epa.gov/echo/cwa_rest_services.get_facility_info",
        "params": {"output": "JSON", "p_st": "VA", "responseset": 5},
    })
    assert_has_rows(out)


def test_live_epa_echo_air_new_york(live_ws):
    """Clean Air Act facilities in New York."""
    out = add_and_run(live_ws, "fetch.epa.echo_facilities", {
        "endpoint": "https://echodata.epa.gov/echo/air_rest_services.get_facility_info",
        "params": {"output": "JSON", "p_st": "NY", "responseset": 5},
    })
    assert_has_rows(out)


def test_live_epa_echo_rcra_texas(live_ws):
    """RCRA hazardous waste facilities in Texas."""
    out = add_and_run(live_ws, "fetch.epa.echo_facilities", {
        "endpoint": "https://echodata.epa.gov/echo/rcra_rest_services.get_facility_info",
        "params": {"output": "JSON", "p_st": "TX", "responseset": 5},
    })
    assert_has_rows(out)


def test_live_epa_echo_air_california(live_ws):
    """Clean Air Act facilities in California (different state than NY test)."""
    out = add_and_run(live_ws, "fetch.epa.echo_facilities", {
        "endpoint": "https://echodata.epa.gov/echo/air_rest_services.get_facility_info",
        "params": {"output": "JSON", "p_st": "CA", "responseset": 5},
    })
    assert_has_rows(out)


def test_live_gsa_calc_ceiling_rates(live_ws):
    out = add_and_run(live_ws, "fetch.gsa_calc.ceiling_rates", {
        "params": {"page": 1, "page_size": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["labor_category"])


def test_live_gsa_calc_default(live_ws):
    """Default ceiling rates listing — no filters."""
    out = add_and_run(live_ws, "fetch.gsa_calc.ceiling_rates", {
        "endpoint": "https://api.gsa.gov/acquisition/calc/v3/api/ceilingrates/",
    })
    assert_has_rows(out)


def test_live_gsa_calc_labor_category_engineer(live_ws):
    """Filter by labor_category 'engineer'."""
    out = add_and_run(live_ws, "fetch.gsa_calc.ceiling_rates", {
        "endpoint": "https://api.gsa.gov/acquisition/calc/v3/api/ceilingrates/",
        "params": {"labor_category": "engineer"},
    })
    assert_has_rows(out)


def test_live_gsa_calc_schedule_mobis(live_ws):
    """Schedule MOBIS rates."""
    out = add_and_run(live_ws, "fetch.gsa_calc.ceiling_rates", {
        "endpoint": "https://api.gsa.gov/acquisition/calc/v3/api/ceilingrates/",
        "params": {"schedule": "MOBIS"},
    })
    assert_has_rows(out)


def test_live_gsa_calc_small_business(live_ws):
    """Small-business filter."""
    out = add_and_run(live_ws, "fetch.gsa_calc.ceiling_rates", {
        "endpoint": "https://api.gsa.gov/acquisition/calc/v3/api/ceilingrates/",
        "params": {"business_size": "s"},
    })
    assert_has_rows(out)


def test_live_naep_adhoc_data(live_ws):
    out = add_and_run(live_ws, "fetch.naep.adhoc_data")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_naep_math_grade4_2022(live_ws):
    """NAEP 4th-grade math composite 2022 (national)."""
    out = add_and_run(live_ws, "fetch.naep.adhoc_data", {
        "endpoint": "https://www.nationsreportcard.gov/Dataservice/GetAdhocData.aspx",
        "params": {
            "type": "data", "subject": "mathematics", "grade": 4,
            "subscale": "MRPCM", "variable": "TOTAL",
            "jurisdiction": "NP", "stattype": "MN:MN", "Year": 2022,
        },
    })
    assert_has_rows(out)


def test_live_naep_reading_grade8_2022(live_ws):
    """NAEP 8th-grade reading composite 2022."""
    out = add_and_run(live_ws, "fetch.naep.adhoc_data", {
        "endpoint": "https://www.nationsreportcard.gov/Dataservice/GetAdhocData.aspx",
        "params": {
            "type": "data", "subject": "reading", "grade": 8,
            "subscale": "RRPCM", "variable": "TOTAL",
            "jurisdiction": "NP", "stattype": "MN:MN", "Year": 2022,
        },
    })
    assert_has_rows(out)


def test_live_naep_math_grade4_trend(live_ws):
    """NAEP 4th-grade math trend across years (multi-year filter)."""
    out = add_and_run(live_ws, "fetch.naep.adhoc_data", {
        "endpoint": "https://www.nationsreportcard.gov/Dataservice/GetAdhocData.aspx",
        "params": {
            "type": "data", "subject": "mathematics", "grade": 4,
            "subscale": "MRPCM", "variable": "TOTAL",
            "jurisdiction": "NP", "stattype": "MN:MN",
            "Year": "2009,2013,2017,2022",
        },
    })
    assert_has_rows(out)


def test_live_naep_math_grade4_top_states(live_ws):
    """NAEP 4th-grade math 2022 — multi-state jurisdiction."""
    out = add_and_run(live_ws, "fetch.naep.adhoc_data", {
        "endpoint": "https://www.nationsreportcard.gov/Dataservice/GetAdhocData.aspx",
        "params": {
            "type": "data", "subject": "mathematics", "grade": 4,
            "subscale": "MRPCM", "variable": "TOTAL",
            "jurisdiction": "CA,TX,NY,FL", "stattype": "MN:MN", "Year": 2022,
        },
    })
    assert_has_rows(out)


def test_live_open_payments(live_ws):
    out = add_and_run(live_ws, "fetch.open_payments.datasets")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


# Mirror name pattern other modules use: test_live_open_payments_datasets_*
def test_live_open_payments_datasets_list(live_ws):
    """List all 74 Open Payments datasets."""
    out = add_and_run(live_ws, "fetch.open_payments.datasets", {
        "endpoint": "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items",
        "params": {"limit": 25},
    })
    assert_has_rows(out)


def test_live_open_payments_datasets_dcat_catalog(live_ws):
    """DCAT-US catalog at /data.json."""
    out = add_and_run(live_ws, "fetch.open_payments.datasets", {
        "endpoint": "https://openpaymentsdata.cms.gov/data.json",
    })
    assert_has_rows(out)


def test_live_open_payments_datasets_query_2018_research(live_ws):
    """Query 2018 Research Payment Data rows by distribution ID."""
    out = add_and_run(live_ws, "fetch.open_payments.datasets", {
        "endpoint": "https://openpaymentsdata.cms.gov/api/1/datastore/query/7b82fb48-2bec-45f0-b40e-aed5f1d1eba0/0",
        "params": {"limit": 25},
    })
    assert_has_rows(out)


def test_live_open_payments_datasets_search_payment(live_ws):
    """Full-text search 'payment'."""
    out = add_and_run(live_ws, "fetch.open_payments.datasets", {
        "endpoint": "https://openpaymentsdata.cms.gov/api/1/search",
        "params": {"fulltext": "payment"},
    })
    assert_has_rows(out)


def test_live_fda_drug_events(live_ws):
    out = add_and_run(live_ws, "fetch.fda.drug_events", {
        "endpoint": "https://api.fda.gov/drug/event.json",
        "params": {"limit": 5},
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_fda_drug_events_top_reactions_to_ibuprofen(live_ws):
    """Top 10 adverse reactions to ibuprofen — exercises `count` facet aggregation."""
    out = add_and_run(live_ws, "fetch.fda.drug_events", {
        "endpoint": "https://api.fda.gov/drug/event.json",
        "params": {
            "search": 'patient.drug.medicinalproduct:"IBUPROFEN"',
            "count": "patient.reaction.reactionmeddrapt.exact",
            "limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Faceted result has `term` and `count` per row.
    assert all(
        r.get("term") and isinstance(r.get("count"), int)
        for r in rows if isinstance(r, dict)
    ), f"expected term/count rows, got {rows[:2]}"


def test_live_fda_drug_events_drug_recalls_class_i(live_ws):
    """Class I drug recalls — most serious classification."""
    out = add_and_run(live_ws, "fetch.fda.drug_events", {
        "endpoint": "https://api.fda.gov/drug/enforcement.json",
        "params": {
            "search": 'classification:"Class I"',
            "limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    assert all(
        r.get("classification") == "Class I" for r in rows if isinstance(r, dict)
    ), f"expected Class I only, got {[r.get('classification') for r in rows[:3]]}"


def test_live_fda_drug_events_food_recalls_class_i(live_ws):
    """Class I food recalls — different endpoint via same module."""
    out = add_and_run(live_ws, "fetch.fda.drug_events", {
        "endpoint": "https://api.fda.gov/food/enforcement.json",
        "params": {
            "search": 'classification:"Class I"',
            "limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    assert all(
        r.get("classification") == "Class I" for r in rows if isinstance(r, dict)
    ), f"expected Class I food recalls"


def test_live_fda_drug_events_adverse_events_january_2024(live_ws):
    """Drug adverse events in January 2024 — date range filter."""
    out = add_and_run(live_ws, "fetch.fda.drug_events", {
        "endpoint": "https://api.fda.gov/drug/event.json",
        "params": {
            "search": "receivedate:[20240101 TO 20240131]",
            "limit": 10,
        },
    })
    assert_has_rows(out)
    rows = out["rows"]
    # Each event should have receivedate in January 2024.
    dates = [r.get("receivedate") for r in rows if isinstance(r, dict)]
    valid = [d for d in dates if isinstance(d, str)]
    assert all(d.startswith("202401") for d in valid), (
        f"expected all dates in 202401, got {valid[:3]}"
    )


def test_live_nhtsa_recalls(live_ws):
    out = add_and_run(live_ws, "fetch.nhtsa.recalls")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_nhtsa_recalls_tesla_model_3_2023(live_ws):
    """Tesla Model 3 2023 recalls — the consumer query."""
    out = add_and_run(live_ws, "fetch.nhtsa.recalls", {
        "endpoint": "https://api.nhtsa.gov/recalls/recallsByVehicle",
        "params": {"make": "Tesla", "model": "Model 3", "modelYear": 2023},
    })
    assert_has_rows(out)


def test_live_nhtsa_recalls_makes_with_2024_recalls(live_ws):
    """All vehicle makes that have 2024 model-year recalls."""
    out = add_and_run(live_ws, "fetch.nhtsa.recalls", {
        "endpoint": "https://api.nhtsa.gov/products/vehicle/makes",
        "params": {"issueType": "r", "modelYear": 2024},
    })
    assert_has_rows(out)
    rows = out["rows"]
    assert len(rows) >= 50, f"expected many makes, got {len(rows)}"


def test_live_nhtsa_recalls_toyota_camry_2022_complaints(live_ws):
    """Toyota Camry 2022 owner complaints — different endpoint."""
    out = add_and_run(live_ws, "fetch.nhtsa.recalls", {
        "endpoint": "https://api.nhtsa.gov/complaints/complaintsByVehicle",
        "params": {"make": "Toyota", "model": "Camry", "modelYear": 2022},
    })
    assert_has_rows(out)


def test_live_nhtsa_recalls_vin_decode(live_ws):
    """Decode a known Honda Accord VIN — different host (vpic.nhtsa.dot.gov)."""
    out = add_and_run(live_ws, "fetch.nhtsa.recalls", {
        "endpoint": "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/1HGCM82633A123456",
        "params": {"format": "json", "modelyear": 2003},
    })
    assert_has_rows(out)


# ── International (no key) ───────────────────────────────────────────────


def test_live_iati(live_ws):
    out = add_and_run(live_ws, "fetch.iati", {"limit": 5})
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_imf_cdis(live_ws):
    out = add_and_run(live_ws, "fetch.imf_cdis")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_wgi(live_ws):
    out = add_and_run(live_ws, "fetch.wgi", {
        "indicators": ["GOV_WGI_CC.EST"],
        "year_min": 2018,
        "year_max": 2022,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["indicator", "country_iso3", "year"])


def test_live_gpi(live_ws):
    out = add_and_run(live_ws, "fetch.gpi")
    assert_output_shape(out, "dataset_ref", "retrieved_at")
    # GPI is a PDF-download-only module; assert the file was downloaded
    raw = out.get("raw", {})
    assert raw.get("size_bytes", 0) > 500_000, (
        f"GPI PDF download too small: {raw.get('size_bytes', 0)} bytes"
    )


def test_live_un_egdi(live_ws):
    out = add_and_run(live_ws, "fetch.un_egdi")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["country_iso2", "year"])


def test_live_rsf_press_freedom(live_ws):
    out = add_and_run(live_ws, "fetch.rsf_press_freedom")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_undp_hdr(live_ws):
    out = add_and_run(live_ws, "fetch.undp_hdr")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_owid_catalog(live_ws):
    # Default fetch (no search) — wrapper paginates up to `limit` charts.
    # Note: full-corpus search is a known wrapper limitation (search filter
    # is applied to the first `limit*3` rows, not the full chart catalog).
    out = add_and_run(live_ws, "fetch.owid_catalog", {
        "limit": 25,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_owid_charts(live_ws):
    out = add_and_run(live_ws, "fetch.owid_charts", {
        "slug": "life-expectancy",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_oecd_sdmx(live_ws):
    out = add_and_run(live_ws, "fetch.oecd_sdmx", {
        "dataset": "current_wellbeing",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_oecd_dac_crs(live_ws):
    out = add_and_run(live_ws, "fetch.oecd_dac_crs")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


# ── Surveys / File manifests (no key) ────────────────────────────────────


def test_live_atus(live_ws):
    out = add_and_run(live_ws, "fetch.atus")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["series_id", "year", "value"])


def test_live_pew(live_ws):
    out = add_and_run(live_ws, "fetch.pew", {"limit": 5})
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["title", "url"])


# ── Geospatial (no key) ─────────────────────────────────────────────────


def test_live_natural_earth(live_ws):
    out = add_and_run(live_ws, "fetch.natural_earth", {
        "level": "adm0",
        "country": "USA",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["name", "iso_a3"])


def test_live_planetary_computer_list(live_ws):
    out = add_and_run(live_ws, "fetch.planetary_computer", {
        "collection": "sentinel-2-l2a",
        "mode": "search",
        "limit": 5,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["id", "collection"])


def test_live_earthdata(live_ws):
    out = add_and_run(live_ws, "fetch.earthdata", {
        "keyword": "MODIS",
        "limit": 5,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["short_name", "title"])


# ── Data.Medicaid.gov (DKAN, no key) ─────────────────────────────────────


def test_live_cms_medicaid_list_all_datasets(live_ws):
    """List all Medicaid open-data datasets."""
    out = add_and_run(live_ws, "fetch.cms.medicaid", {
        "endpoint": "https://data.medicaid.gov/api/1/metastore/schemas/dataset/items",
        "params": {"limit": 25},
    })
    assert_output_shape(out, "dataset_ref", "endpoint", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_cms_medicaid_dcat_catalog(live_ws):
    """DCAT-US JSON-LD catalog."""
    out = add_and_run(live_ws, "fetch.cms.medicaid", {
        "endpoint": "https://data.medicaid.gov/data.json",
    })
    assert_has_rows(out)


def test_live_cms_medicaid_drug_utilization_1991(live_ws):
    """State Drug Utilization Data 1991."""
    out = add_and_run(live_ws, "fetch.cms.medicaid", {
        "endpoint": "https://data.medicaid.gov/api/1/datastore/query/ae4d5347-5137-5f6c-b66c-3420fa0316d8/0",
        "params": {"limit": 25},
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # Drug utilization rows have NDC + state + utilization_type
    assert "ndc" in sample, (
        f"expected NDC in drug utilization row, got keys {list(sample.keys())[:8]}"
    )


def test_live_cms_medicaid_search_enrollment(live_ws):
    """Full-text search for enrollment datasets."""
    out = add_and_run(live_ws, "fetch.cms.medicaid", {
        "endpoint": "https://data.medicaid.gov/api/1/search",
        "params": {"fulltext": "enrollment"},
    })
    assert_has_rows(out)


def test_live_cms_medicaid_search_managed_care(live_ws):
    """Full-text search for managed care datasets."""
    out = add_and_run(live_ws, "fetch.cms.medicaid", {
        "endpoint": "https://data.medicaid.gov/api/1/search",
        "params": {"fulltext": "managed care"},
    })
    assert_has_rows(out)


# ── EPA Toxics Release Inventory (Envirofacts, no key) ──────────────────


def test_live_epa_tri_facilities_california(live_ws):
    """TRI facilities in California — default endpoint top 25 rows."""
    out = add_and_run(live_ws, "fetch.epa.tri")
    assert_output_shape(out, "dataset_ref", "endpoint", "rows", "retrieved_at")
    assert_has_rows(out)
    sample = out["rows"][0]
    assert sample.get("state_abbr") == "CA", (
        f"expected CA facility, got {sample.get('state_abbr')!r}"
    )


def test_live_epa_tri_facilities_los_angeles_county(live_ws):
    """TRI facilities in Los Angeles County."""
    out = add_and_run(live_ws, "fetch.epa.tri", {
        "endpoint": "https://data.epa.gov/efservice/tri_facility/state_abbr/CA/county_name/LOS%20ANGELES/Rows/0:25/JSON",
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    assert sample.get("county_name", "").upper() == "LOS ANGELES", (
        f"expected LA county, got {sample.get('county_name')!r}"
    )


def test_live_epa_tri_form_r_california_2022(live_ws):
    """TRI Form R annual release reports — California 2022."""
    out = add_and_run(live_ws, "fetch.epa.tri", {
        "endpoint": "https://data.epa.gov/efservice/tri_form_r/state_abbr/CA/reporting_year/2022/Rows/0:25/JSON",
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # Form R reports have a doc_ctrl_num and a reporting year
    assert "doc_ctrl_num" in sample, (
        f"expected doc_ctrl_num in Form R row, got keys {list(sample.keys())[:8]}"
    )


def test_live_epa_tri_chemical_lookup_lead(live_ws):
    """TRI chemical info for Lead (CAS 7439-92-1)."""
    out = add_and_run(live_ws, "fetch.epa.tri", {
        "endpoint": "https://data.epa.gov/efservice/tri_chem_info/cas/7439-92-1/JSON",
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # Returns chemical metadata; chem_name should be present
    assert "chem_name" in sample, (
        f"expected chem_name in TRI chem row, got keys {list(sample.keys())[:8]}"
    )


def test_live_epa_tri_facilities_texas(live_ws):
    """TRI facilities in Texas."""
    out = add_and_run(live_ws, "fetch.epa.tri", {
        "endpoint": "https://data.epa.gov/efservice/tri_facility/state_abbr/TX/Rows/0:25/JSON",
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    assert sample.get("state_abbr") == "TX", (
        f"expected TX facility, got {sample.get('state_abbr')!r}"
    )


# ── NOAA NWS (api.weather.gov, no key) ───────────────────────────────────


def test_live_noaa_nws_alerts_active_ca(live_ws):
    """All currently active weather alerts in California."""
    out = add_and_run(live_ws, "fetch.noaa.nws", {
        "endpoint": "https://api.weather.gov/alerts/active",
        "params": {"area": "CA"},
    })
    assert_output_shape(out, "dataset_ref", "endpoint", "rows", "retrieved_at")
    raw = out.get("raw") or {}
    # Confirm raw is a GeoJSON FeatureCollection — even if no alerts active
    # right now, the response shape proves the call succeeded.
    assert raw.get("type") == "FeatureCollection", (
        f"expected FeatureCollection, got type={raw.get('type')!r}"
    )


def test_live_noaa_nws_alerts_active_nationwide(live_ws):
    """Nationwide active alerts — there's almost always >=1 active in the US."""
    out = add_and_run(live_ws, "fetch.noaa.nws", {
        "endpoint": "https://api.weather.gov/alerts/active",
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # Each alert is a GeoJSON Feature with a 'properties' dict.
    assert sample.get("type") == "Feature", (
        f"expected Feature row type, got {sample.get('type')!r}"
    )
    props = sample.get("properties") or {}
    assert "event" in props, (
        f"expected alert event in properties, got keys {list(props.keys())[:8]}"
    )


def test_live_noaa_nws_point_forecast_dc(live_ws):
    """NWS point lookup for Washington DC — returns office + grid coordinates."""
    out = add_and_run(live_ws, "fetch.noaa.nws", {
        "endpoint": "https://api.weather.gov/points/38.8894,-77.0352",
    })
    assert_has_rows(out)
    # Point response: properties wrapped in a list of length 1.
    sample = out["rows"][0]
    assert "gridId" in sample, (
        f"expected gridId in point response, got keys {list(sample.keys())[:8]}"
    )
    assert sample.get("gridId") in ("LWX", "MTR"), (
        f"DC should map to LWX (or MTR), got {sample.get('gridId')!r}"
    )


def test_live_noaa_nws_stations_california(live_ws):
    """List NWS observation stations in California."""
    out = add_and_run(live_ws, "fetch.noaa.nws", {
        "endpoint": "https://api.weather.gov/stations",
        "params": {"state": "CA", "limit": 25},
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    props = sample.get("properties") or {}
    # Stations don't expose 'state' directly; the county URL is /zones/county/CAC###
    county_url = props.get("county") or ""
    assert "/CAC" in county_url, (
        f"expected CA county zone (/zones/county/CAC###) in station, "
        f"got county={county_url!r}"
    )


def test_live_noaa_nws_zones_california(live_ws):
    """List forecast zones for California."""
    out = add_and_run(live_ws, "fetch.noaa.nws", {
        "endpoint": "https://api.weather.gov/zones",
        "params": {"area": "CA", "type": "forecast", "limit": 25},
    })
    assert_has_rows(out)


def test_live_noaa_nws_latest_observation_dca(live_ws):
    """Latest weather observation at Reagan National Airport (KDCA)."""
    out = add_and_run(live_ws, "fetch.noaa.nws", {
        "endpoint": "https://api.weather.gov/stations/KDCA/observations/latest",
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # Observation rows have a 'station' identifier and a 'temperature' field.
    assert "station" in sample, (
        f"expected station ref in observation, got keys {list(sample.keys())[:10]}"
    )
