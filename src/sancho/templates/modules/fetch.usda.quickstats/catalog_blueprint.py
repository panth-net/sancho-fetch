from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.usda.quickstats"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://quickstats.nass.usda.gov/api"
DOCS_URL = "https://quickstats.nass.usda.gov/api"


# Quickstats query params. Categorical dimensions can be enumerated via
# /api/get_param_values/?param=X and are inlined into catalog.json.
ENUMERABLE_PARAMS: list[str] = [
    "source_desc",          # CENSUS / SURVEY
    "sector_desc",          # ANIMALS & PRODUCTS, CROPS, DEMOGRAPHICS, ECONOMICS, ENVIRONMENTAL
    "group_desc",           # ~50 commodity groups
    "commodity_desc",       # ~500 commodities
    "class_desc",           # ~3,500 variety/class subdivisions
    "prodn_practice_desc",  # production practice
    "util_practice_desc",   # utilization practice
    "statisticcat_desc",    # measurement category (YIELD, PRODUCTION, AREA PLANTED, ...)
    "unit_desc",            # ~500 units
    "short_desc",           # fully-qualified data series name
    "domain_desc",          # ~30 domains
    "domaincat_desc",       # many
    "agg_level_desc",       # NATIONAL, STATE, COUNTY, REGION: MULTI-STATE, ...
    "state_alpha",          # 56 state codes
    "state_name",           # 56 state names
    "region_desc",          # ~30 regions
    "freq_desc",            # ANNUAL, MONTHLY, WEEKLY, POINT IN TIME
    "reference_period_desc",  # ~60 reference periods
    "country_name",         # countries with Ag/Econ data
]


# Non-enumerable params (documented but not fetched -- they're free-form or huge).
NON_ENUMERABLE_PARAMS: dict[str, dict[str, Any]] = {
    "key": {"type": "string", "description": "USDA_NASS_API_KEY"},
    "year": {"type": "string", "description": "Year or comma-separated list"},
    "year__GE": {"type": "string", "description": "Year >=" },
    "year__LE": {"type": "string", "description": "Year <="},
    "state_ansi": {"type": "string", "description": "State ANSI code (2-digit)"},
    "county_ansi": {"type": "string", "description": "County ANSI code"},
    "county_name": {"type": "string", "description": "County name"},
    "congr_district_code": {"type": "string", "description": "Congressional district"},
    "zip_5": {"type": "string", "description": "ZIP5 code"},
    "watershed_code": {"type": "string", "description": "HUC-8 watershed code"},
    "week_ending": {"type": "string", "description": "ISO date for weekly data"},
    "format": {"type": "string", "description": "Response format", "examples": ["JSON", "CSV", "XML"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "api.data",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/api_GET/"],
            "methods": ["GET"],
            "query_params": NON_ENUMERABLE_PARAMS,
            "response_mode": "json",
            "envelope_key": "data",
            "description": "Primary data query. Filter by combinations of enumerable params (see catalog.json.parameters) + free-form year/geo filters.",
            "source_refs": refs,
        },
        {
            "id": "api.count",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/get_counts/"],
            "methods": ["GET"],
            "query_params": NON_ENUMERABLE_PARAMS,
            "response_mode": "json",
            "envelope_key": "count",
            "description": "Plan pagination: returns row count for a given filter.",
            "source_refs": refs,
        },
        {
            "id": "meta.param_values",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/get_param_values/"],
            "methods": ["GET"],
            "query_params": {"param": {"type": "string", "description": "Parameter name to enumerate"}, "key": {"type": "string"}},
            "response_mode": "json",
            "envelope_key": "{param}",
            "description": "Enumerate every valid value for a given param. See catalog.json.parameters for the inlined results.",
            "source_refs": refs,
        },
    ]
