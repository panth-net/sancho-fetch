from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.planetary_computer"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
DOCS_URL = "https://planetarycomputer.microsoft.com/docs/reference/stac/"
META_COLLECTIONS = "/collections"

STAC_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "collections": {"type": "list[string]", "description": "Collection IDs to query", "examples": [["sentinel-2-l2a"]]},
    "ids": {"type": "list[string]", "description": "Specific item IDs"},
    "bbox": {"type": "list[float]", "description": "[minLon, minLat, maxLon, maxLat]"},
    "intersects": {"type": "object", "description": "GeoJSON geometry filter"},
    "datetime": {"type": "string", "description": "ISO 8601 instant or range", "examples": ["2024-01-01/2024-12-31"]},
    "limit": {"type": "int", "description": "Max items per page (default 10, max 1000)"},
    "query": {"type": "object", "description": "STAC property filters"},
    "fields": {"type": "object", "description": "Include/exclude properties"},
    "sortby": {"type": "list[object]", "description": "Sort expression"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "stac.search",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/search"],
            "methods": ["GET", "POST"],
            "query_params": STAC_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "features",
            "description": "STAC item search across all 135 Planetary Computer collections.",
            "source_refs": refs,
        },
        {
            "id": "stac.collection",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_COLLECTIONS, "/collections/{collection_id}"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "collections",
            "description": "STAC collection metadata. See catalog.json.collections.",
            "source_refs": refs,
        },
        {
            "id": "stac.collection_items",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/collections/{collection_id}/items", "/collections/{collection_id}/items/{item_id}"],
            "methods": ["GET"],
            "query_params": STAC_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "features",
            "description": "Items within one STAC collection.",
            "source_refs": refs,
        },
    ]
