from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.eia.series"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.eia.gov/v2"
DOCS_URL = "https://www.eia.gov/opendata/documentation.php"


DATA_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "api_key": {"type": "string", "description": "EIA_API_KEY"},
    "frequency": {"type": "string", "description": "Frequency", "examples": ["daily", "weekly", "monthly", "quarterly", "annual"]},
    "data[]": {"type": "list[string]", "description": "Data column(s) to return (see catalog.json.routes[].facets.columns)"},
    "facets[{dim}][]": {"type": "list[string]", "description": "Facet filter by dimension"},
    "start": {"type": "string", "description": "Earliest period"},
    "end": {"type": "string", "description": "Latest period"},
    "sort[0][column]": {"type": "string"},
    "sort[0][direction]": {"type": "string", "examples": ["asc", "desc"]},
    "offset": {"type": "int", "description": "Pagination offset"},
    "length": {"type": "int", "description": "Page size (max 5000)"},
    "out": {"type": "string", "description": "Response format", "examples": ["json", "xml"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "data",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/{route_path}/data"],
            "methods": ["GET", "POST"],
            "query_params": DATA_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "response.data",
            "description": "Query any EIA dataset. See catalog.json.routes for the full route tree + facet schema per dataset.",
            "source_refs": refs,
        },
        {
            "id": "meta.route",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/", "/{route_path}"],
            "methods": ["GET"],
            "query_params": {"api_key": {"type": "string"}},
            "response_mode": "json",
            "envelope_key": "response",
            "description": "Route discovery. Each response lists sub-routes + available frequencies/facets at that level.",
            "source_refs": refs,
        },
        {
            "id": "meta.facet",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/{route_path}/facet/{facet_name}"],
            "methods": ["GET"],
            "query_params": {"api_key": {"type": "string"}},
            "response_mode": "json",
            "envelope_key": "response.facets",
            "description": "Enumerate facet values (e.g. region codes, fuel types) for a specific route+dimension.",
            "source_refs": refs,
        },
    ]
