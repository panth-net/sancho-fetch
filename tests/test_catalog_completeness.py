"""Guard against catalog regression to skeleton data.

Every live-discovery module (fetch.* with discovery.py) must have
catalog.meta.json stats at or above well-known minimums. This traps the
kind of silent skeleton-state regression we hit with fetch.world_bank
(indicator_count: 2 when the real API has ~29,000).

Refresh a stale catalog with:

    python -c "from pathlib import Path; from sancho.provider_discovery import run_module_discovery; \\
        run_module_discovery(Path('src/sancho/templates/modules/<module_id>'))"
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "sancho" / "templates" / "modules"

# Minimum expected stat thresholds for each live-discovery module. Values are
# conservative (~half the real count observed on 2026-04-14) so normal
# provider churn does not fail the test, but skeleton data (single-digit
# counts) will.
MIN_STATS: dict[str, dict[str, int]] = {
    "fetch.world_bank": {
        "indicator_count": 10000,
        "source_count": 30,
        "country_count": 200,
        "topic_count": 10,
    },
    "fetch.cdc": {
        "family_count": 10,
        "catalog_sample_count": 500,
    },
    "fetch.nyc_open_data": {
        "dataset_count": 1000,
        "asset_count": 1500,
        "column_count": 20000,
    },
    "fetch.bls": {
        "family_count": 3,
        "surveys_count": 30,
    },
    "fetch.fec": {
        "family_count": 80,
    },
    "fetch.fema.openfema": {
        "dataset_count": 30,
        "field_count": 800,
        "family_count": 3,
    },
    "fetch.clinical_trials.studies": {
        "field_count": 300,
        "enum_type_count": 20,
        "enum_value_count": 100,
        "family_count": 5,
    },
    "fetch.socrata.chicago_crimes": {
        "asset_count": 1000,
        "dataset_count": 400,
    },
    "fetch.socrata.la_crime": {
        "asset_count": 500,
        "dataset_count": 150,
    },
    "fetch.socrata.sf_building_permits": {
        "asset_count": 3,  # SF is lightly federated; real domain is larger but Socrata catalog only exposes a handful
    },
    "fetch.socrata.seattle_building_permits": {
        "asset_count": 150,
    },
    "fetch.usgs.earthquakes": {
        "catalog_count": 30,
        "eventtype_count": 20,
        "magnitudetype_count": 20,
        "producttype_count": 30,
    },
    "fetch.federal_register.documents": {
        "agency_count": 300,
        "facet_count": 5,
        "facet_topic_bucket_count": 500,
    },
    "fetch.usaspending.awards": {
        "reference_count": 5,
        "toptier_agencies_count": 50,
        "glossary_count": 100,
        "def_codes_count": 20,
    },
    "fetch.cms.data": {
        "dataset_count": 100,
        "distribution_count": 3000,
    },
    "fetch.open_payments.datasets": {
        "dataset_count": 40,
    },
    "fetch.fda.drug_events": {
        "category_count": 5,
        "endpoint_count": 20,
    },
    "fetch.sec.company_submissions": {
        "company_count": 8000,
    },
    "fetch.nhtsa.recalls": {
        "make_count": 8000,
        "variable_count": 100,
    },
    "fetch.census.acs_profile": {
        "dataset_count": 1000,
    },
    "fetch.fred.series": {
        "release_count": 200,
        "source_count": 80,
        "tag_count": 4000,
    },
    "fetch.planetary_computer": {
        "collection_count": 80,
    },
    "fetch.noaa.cdo": {
        "dataset_count": 5,
        "data_category_count": 20,
        "data_type_count": 800,
    },
    "fetch.earthdata": {
        "provider_count": 30,
        "collection_sample_count": 1500,
        "collections_total_in_cmr": 40000,
    },
    "fetch.epa.echo_facilities": {
        "service_count": 4,
        "column_count": 400,
    },
    "fetch.iati": {
        "codelist_count": 50,
        "total_codelist_entries": 2000,
    },
    "fetch.hud.fmr": {
        "state_count": 50,
        "metro_area_count": 300,
        "county_count": 2000,
    },
    "fetch.bea.nipa_table": {
        "dataset_count": 10,
        "total_parameter_count": 30,
    },
    "fetch.congress.bills": {
        "resource_count": 15,
        "successful_resources": 15,
        "congress_count": 100,
    },
    "fetch.fdic.institutions": {
        "resource_count": 3,
        "total_field_count": 200,
    },
    "fetch.usda.fooddata_search": {
        "data_type_count": 4,
        "field_count": 10,
        "total_food_count": 100000,
    },
    "fetch.usda.quickstats": {
        "parameter_count": 15,
        "total_value_count": 30000,
    },
    "fetch.oecd_sdmx": {
        "dataflow_count": 1000,
        "agency_count": 30,
    },
    "fetch.oecd_dac_crs": {
        "dataflow_count": 8,
    },
    "fetch.imf_cdis": {
        "dataflow_count": 50,
    },
    "fetch.cfpb.complaints": {
        "aggregation_count": 10,
        "total_bucket_count": 3000,
        "field_count": 15,
    },
    "fetch.college_scorecard.schools": {
        "total_schools": 5000,
        "field_path_count": 2000,
    },
    "fetch.eia.series": {
        "route_count": 100,
        "leaf_route_count": 100,
        "total_data_column_count": 200,
    },
    "fetch.epa.aqs_annual": {
        "list_count": 4,
        "total_parameter_count": 1000,
    },
    "fetch.nrel.alt_fuel_stations": {
        "total_stations": 50000,
        "field_count": 50,
        "fuel_type_count": 5,
    },
    "fetch.doj.press_releases": {
        "content_type_count": 1,
        "total_record_count": 100000,
    },
}


@pytest.mark.parametrize("module_id,thresholds", list(MIN_STATS.items()))
def test_catalog_is_not_skeleton(module_id: str, thresholds: dict[str, int]) -> None:
    meta_path = TEMPLATES / module_id / "catalog.meta.json"
    assert meta_path.exists(), f"{module_id}: catalog.meta.json is missing"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    stats = meta.get("stats")
    assert isinstance(stats, dict), f"{module_id}: catalog.meta.json has no 'stats' dict"

    for key, minimum in thresholds.items():
        actual = stats.get(key, 0)
        assert isinstance(actual, int), f"{module_id}: stats.{key} is {type(actual).__name__}, expected int"
        assert actual >= minimum, (
            f"{module_id} catalog looks like skeleton data: stats.{key}={actual}, "
            f"expected >= {minimum}. Refresh with run_module_discovery against the template dir."
        )
