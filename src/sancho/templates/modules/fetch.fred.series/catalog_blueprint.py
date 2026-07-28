from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.fred.series"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.stlouisfed.org/fred"
DOCS_URL = "https://fred.stlouisfed.org/docs/api/fred/"

META_RELEASES = "/releases"
META_SOURCES = "/sources"
META_TAGS = "/tags"
META_CATEGORY_CHILDREN = "/category/children"


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "api_key": {"type": "string", "description": "FRED_API_KEY"},
    "file_type": {"type": "string", "description": "Response format", "examples": ["json", "xml"]},
    "realtime_start": {"type": "string", "description": "Vintage-date start", "examples": ["2024-01-01"]},
    "realtime_end": {"type": "string", "description": "Vintage-date end", "examples": ["2024-12-31"]},
    "limit": {"type": "int", "description": "Page size (max 100000)", "examples": [1000, 100000]},
    "offset": {"type": "int", "description": "Pagination offset", "examples": [0, 1000]},
    "order_by": {"type": "string", "description": "Sort field"},
    "sort_order": {"type": "string", "description": "asc or desc"},
}

SERIES_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    **COMMON_QUERY_PARAMS,
    "observation_start": {"type": "string", "description": "Earliest observation date"},
    "observation_end": {"type": "string", "description": "Latest observation date"},
    "units": {"type": "string", "description": "Unit transformation", "examples": ["lin", "chg", "ch1", "pch", "pc1", "pca"]},
    "frequency": {"type": "string", "description": "Aggregation frequency", "examples": ["d", "w", "bw", "m", "q", "sa", "a"]},
    "aggregation_method": {"type": "string", "description": "Aggregation method", "examples": ["avg", "sum", "eop"]},
    "output_type": {"type": "int", "description": "Vintage output type", "examples": [1, 2, 3, 4]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "series.observations",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/series/observations"],
            "methods": ["GET"],
            "query_params": {**SERIES_QUERY_PARAMS, "series_id": {"type": "string", "description": "FRED series ID (required)", "examples": ["GDP", "UNRATE"]}},
            "response_mode": "json",
            "envelope_key": "observations",
            "description": "Observation timeseries for one FRED series. See catalog.json.releases for how to find series IDs.",
            "source_refs": refs,
        },
        {
            "id": "series",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/series", "/series/search", "/series/search/tags", "/series/release"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "seriess",
            "description": "Search/enumerate FRED series by ID, free text, tags, or release.",
            "source_refs": refs,
        },
        {
            "id": "categories",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [
                "/category", "/category/children", "/category/related",
                "/category/series", "/category/tags",
            ],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "",
            "description": "Hierarchical category tree. catalog.json.categories contains the top-level children of the root (category_id=0).",
            "source_refs": refs,
        },
        {
            "id": "meta.releases",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_RELEASES, "/release", "/release/series"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "releases",
            "description": "All FRED releases. See catalog.json.releases.",
            "source_refs": refs,
        },
        {
            "id": "meta.sources",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_SOURCES, "/source", "/source/releases"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "sources",
            "description": "All FRED source organisations.",
            "source_refs": refs,
        },
        {
            "id": "meta.tags",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_TAGS, "/related_tags", "/tags/series"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "tags",
            "description": "All FRED tags for search/faceting.",
            "source_refs": refs,
        },
    ]
