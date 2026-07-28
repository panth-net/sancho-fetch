from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.earthdata"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://cmr.earthdata.nasa.gov"
DOCS_URL = "https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html"

META_PROVIDERS = "/ingest/providers"
META_COLLECTIONS = "/search/collections.json"


CMR_SEARCH_PARAMS: dict[str, dict[str, Any]] = {
    "provider": {"type": "string", "description": "Data provider short name", "examples": ["GES_DISC", "LPDAAC_ECS", "PODAAC"]},
    "short_name": {"type": "string", "description": "Collection short-name filter"},
    "keyword": {"type": "string", "description": "Free-text search across dataset_id/title/summary"},
    "temporal": {"type": "string", "description": "ISO 8601 temporal range", "examples": ["2020-01-01T00:00:00Z,2024-12-31T23:59:59Z"]},
    "bounding_box": {"type": "string", "description": "WSWESN or WSWE,NS,EN -- lon,lat,lon,lat", "examples": ["-180,-90,180,90"]},
    "point": {"type": "string", "description": "lon,lat point query"},
    "polygon": {"type": "string", "description": "Polygon WKT-ish"},
    "instrument": {"type": "string", "description": "Instrument filter"},
    "platform": {"type": "string", "description": "Platform filter"},
    "concept_id": {"type": "string", "description": "CMR concept-id filter"},
    "page_size": {"type": "int", "description": "Results per page (max 2000)", "examples": [100, 1000, 2000]},
    "page_num": {"type": "int", "description": "1-based page number"},
    "offset": {"type": "int", "description": "Alternative offset-based pagination"},
    "sort_key": {"type": "string", "description": "Sort expression", "examples": ["-start_date", "entry_title"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "search.collections",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/search/collections.json", "/search/collections.umm_json", "/search/collections.atom"],
            "methods": ["GET", "POST"],
            "query_params": CMR_SEARCH_PARAMS,
            "response_mode": "json",
            "envelope_key": "feed.entry",
            "description": "Collection search across 54,000+ NASA EOSDIS datasets. Total count in CMR-Hits response header.",
            "source_refs": refs,
        },
        {
            "id": "search.granules",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/search/granules.json", "/search/granules.umm_json"],
            "methods": ["GET", "POST"],
            "query_params": {**CMR_SEARCH_PARAMS, "collection_concept_id": {"type": "string", "description": "Parent collection concept-id (required)"}},
            "response_mode": "json",
            "envelope_key": "feed.entry",
            "description": "Granule-level (individual file/scene) search within a collection.",
            "source_refs": refs,
        },
        {
            "id": "search.variables",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/search/variables.json", "/search/variables.umm_json"],
            "methods": ["GET", "POST"],
            "query_params": CMR_SEARCH_PARAMS,
            "response_mode": "json",
            "envelope_key": "items",
            "description": "Variable-level metadata (bands, channels, parameters) within collections.",
            "source_refs": refs,
        },
        {
            "id": "meta.providers",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_PROVIDERS],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "All CMR data providers (60 organisations: GES_DISC, PODAAC, LP DAAC, NSIDC, etc.). See catalog.json.providers.",
            "source_refs": refs,
        },
    ]
