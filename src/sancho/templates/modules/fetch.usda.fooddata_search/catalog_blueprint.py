from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.usda.fooddata_search"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.nal.usda.gov/fdc/v1"
DOCS_URL = "https://fdc.nal.usda.gov/api-guide.html"


# Known FoodData Central data types. These are NOT returned by a list
# endpoint -- they come from the published API guide.
DATA_TYPES: list[str] = [
    "Branded",       # branded food products
    "Foundation",    # Foundation Foods
    "Survey (FNDDS)",  # Food and Nutrient Database for Dietary Studies
    "SR Legacy",     # Standard Reference (legacy)
    "Experimental",  # experimental
]


SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "api_key": {"type": "string", "description": "DATA_GOV_API_KEY"},
    "query": {"type": "string", "description": "Free-text search expression", "examples": ["apple", "milk+whole"]},
    "dataType": {"type": "string", "description": "Comma-separated data types"},
    "pageSize": {"type": "int", "description": "Results per page (max 200)"},
    "pageNumber": {"type": "int", "description": "1-based page number"},
    "sortBy": {"type": "string", "description": "Sort field", "examples": ["dataType.keyword", "publishedDate", "fdcId"]},
    "sortOrder": {"type": "string", "description": "asc or desc"},
    "brandOwner": {"type": "string", "description": "Brand owner filter (Branded)"},
    "tradeChannel": {"type": "list[string]", "description": "Trade channel filter"},
    "startDate": {"type": "string", "description": "Publication start date"},
    "endDate": {"type": "string", "description": "Publication end date"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "foods.search",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/foods/search"],
            "methods": ["GET", "POST"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "foods",
            "description": "Full-text search across all food records. Total count returned in 'totalHits'.",
            "source_refs": refs,
        },
        {
            "id": "foods.list",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/foods/list"],
            "methods": ["GET", "POST"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "",
            "description": "Paginated list of foods (unfiltered + sorted).",
            "source_refs": refs,
        },
        {
            "id": "food.single",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/food/{fdcId}", "/foods"],
            "methods": ["GET", "POST"],
            "query_params": {**SEARCH_QUERY_PARAMS, "fdcIds": {"type": "list[string]", "description": "Up to 20 FDC IDs (POST /foods)"}, "format": {"type": "string", "examples": ["abridged", "full"]}, "nutrients": {"type": "list[int]", "description": "Restrict response to specific nutrient IDs"}},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Full record for one or multiple foods by fdcId.",
            "source_refs": refs,
        },
    ]
