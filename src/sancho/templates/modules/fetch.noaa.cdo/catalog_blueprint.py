from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.noaa.cdo"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2"
DOCS_URL = "https://www.ncdc.noaa.gov/cdo-web/webservices/v2"

COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "datasetid": {"type": "string", "description": "Filter by dataset ID", "examples": ["GHCND", "GSOM", "NORMAL_DLY"]},
    "datacategoryid": {"type": "string", "description": "Filter by data category"},
    "datatypeid": {"type": "string", "description": "Filter by data type"},
    "locationid": {"type": "string", "description": "Filter by location ID"},
    "stationid": {"type": "string", "description": "Filter by station ID"},
    "startdate": {"type": "string", "description": "ISO date lower bound"},
    "enddate": {"type": "string", "description": "ISO date upper bound"},
    "units": {"type": "string", "description": "Unit system", "examples": ["standard", "metric"]},
    "sortfield": {"type": "string", "description": "Sort field"},
    "sortorder": {"type": "string", "description": "asc or desc"},
    "limit": {"type": "int", "description": "Results per page (max 1000)"},
    "offset": {"type": "int", "description": "Pagination offset (1-based)"},
    "includemetadata": {"type": "string", "description": "Include response metadata"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "data",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/data"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Actual observation records. Requires datasetid + startdate + enddate + (stationid|locationid).",
            "source_refs": refs,
        },
        {
            "id": "meta.datasets",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/datasets", "/datasets/{id}"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "All 11 NOAA datasets (GHCND, GSOM, etc.). See catalog.json.datasets.",
            "source_refs": refs,
        },
        {
            "id": "meta.datacategories",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/datacategories"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Data categories (e.g. TEMP, PRCP). See catalog.json.data_categories.",
            "source_refs": refs,
        },
        {
            "id": "meta.datatypes",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/datatypes"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "1,566 data types (TMIN, TMAX, PRCP, etc.). See catalog.json.data_types.",
            "source_refs": refs,
        },
        {
            "id": "meta.locationcategories",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/locationcategories"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Location categories (CITY, STATE, COUNTRY, ...).",
            "source_refs": refs,
        },
        {
            "id": "meta.locations",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/locations", "/locations/{id}"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Locations (FIPS/ZIP/climate divisions). Paginated; huge, not inlined.",
            "source_refs": refs,
        },
        {
            "id": "meta.stations",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/stations", "/stations/{id}"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "154,000+ weather stations. Paginate via offset/limit -- NOT inlined in catalog.json (too large).",
            "source_refs": refs,
        },
    ]
