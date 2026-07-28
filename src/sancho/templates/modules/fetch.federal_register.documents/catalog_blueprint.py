from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.federal_register.documents"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://www.federalregister.gov/api/v1"
DOCS_URL = "https://www.federalregister.gov/developers/api/v1"

META_AGENCIES = "/agencies.json"
FACETS_BASE = "/documents/facets"
FACET_KEYS = ["agency", "topic", "section", "type", "subtype"]


SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "conditions[term]": {"type": "string", "description": "Free-text search across title + abstract"},
    "conditions[agencies][]": {"type": "string", "description": "Agency slug filter (repeatable)"},
    "conditions[type][]": {"type": "string", "description": "Document type filter", "examples": ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]},
    "conditions[publication_date][gte]": {"type": "string", "description": "Earliest publication date (YYYY-MM-DD)"},
    "conditions[publication_date][lte]": {"type": "string", "description": "Latest publication date (YYYY-MM-DD)"},
    "conditions[publication_date][year]": {"type": "int", "description": "Restrict to a single publication year"},
    "conditions[topics][]": {"type": "string", "description": "Topic slug filter (repeatable)"},
    "conditions[sections][]": {"type": "string", "description": "Section slug filter (repeatable)"},
    "conditions[cfr][title]": {"type": "int", "description": "CFR title number"},
    "conditions[cfr][part]": {"type": "int", "description": "CFR part number"},
    "fields[]": {"type": "string", "description": "Specific fields to return (repeatable)"},
    "per_page": {"type": "int", "description": "Page size (max 1000)", "examples": [100, 1000]},
    "page": {"type": "int", "description": "Page number", "examples": [1, 2]},
    "order": {"type": "string", "description": "Sort order", "examples": ["newest", "relevance"]},
    "format": {"type": "string", "description": "Response format", "examples": ["json", "csv"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "documents",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/documents.json", "/documents/{document_number}.json"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Federal Register published documents. Results are capped at 10,000 per query -- window by publication_date.",
            "source_refs": refs,
        },
        {
            "id": "public_inspection",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/public-inspection-documents.json", "/public-inspection-documents/current.json"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Documents available for public inspection before publication.",
            "source_refs": refs,
        },
        {
            "id": "meta.agencies",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_AGENCIES, "/agencies/{slug}"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Agencies that publish documents. See catalog.json.agencies.",
            "source_refs": refs,
        },
        {
            "id": "meta.facets",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [f"{FACETS_BASE}/{{facet}}"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": f"Faceted enumerations: {', '.join(FACET_KEYS)}. See catalog.json.facets.",
            "source_refs": refs,
        },
    ]
