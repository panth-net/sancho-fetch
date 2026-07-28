from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.doj.press_releases"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://www.justice.gov/api/v1"
DOCS_URL = "https://www.justice.gov/developer"


SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "pagesize": {"type": "int", "description": "Page size (max 50)"},
    "page": {"type": "int", "description": "Pagination offset (0-based)"},
    "sort": {"type": "string", "description": "Sort field"},
    "direction": {"type": "string", "examples": ["asc", "desc"]},
    "title": {"type": "string", "description": "Title keyword filter"},
    "date_start": {"type": "string", "description": "ISO date filter"},
    "date_end": {"type": "string", "description": "ISO date filter"},
    "topic": {"type": "string", "description": "Topic slug"},
    "component": {"type": "string", "description": "DOJ component slug"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "press_releases",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/press_releases.json", "/press_releases/{uuid}.json"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "DOJ press releases. Total count in metadata.resultset.count.",
            "source_refs": refs,
        },
        {
            "id": "blog_entries",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/blog_entries.json", "/blog_entries/{uuid}.json"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "DOJ blog entries.",
            "source_refs": refs,
        },
        {
            "id": "speeches",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/speeches.json", "/speeches/{uuid}.json"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "DOJ speeches.",
            "source_refs": refs,
        },
    ]
