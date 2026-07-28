from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.usaspending.awards"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.usaspending.gov/api/v2"
DOCS_URL = "https://api.usaspending.gov/"

META_ENDPOINTS: list[tuple[str, str, str]] = [
    # (key, path, envelope key that holds the list)
    ("toptier_agencies", "/references/toptier_agencies/", "results"),
    ("award_types", "/references/award_types/", ""),
    ("glossary", "/references/glossary/?limit=500", "results"),
    ("def_codes", "/references/def_codes/", "codes"),
    ("cfda_totals", "/references/cfda/totals/", "results"),
    ("filter_tree_psc", "/references/filter_tree/psc/", "results"),
    ("filter_tree_naics", "/references/filter_tree/naics/", "results"),
    ("filter_tree_tas", "/references/filter_tree/tas/", "results"),
]


SEARCH_BODY_PARAMS: dict[str, dict[str, Any]] = {
    "filters.time_period": {"type": "list[object]", "description": "List of {start_date, end_date} objects"},
    "filters.award_type_codes": {"type": "list[string]", "description": "Award-type codes", "examples": [["A", "B", "C", "D"], ["10"]]},
    "filters.agencies": {"type": "list[object]", "description": "List of {type, tier, name} agency filters"},
    "filters.naics_codes": {"type": "list[string]", "description": "NAICS code filter"},
    "filters.psc_codes": {"type": "list[string]", "description": "Product Service Code filter"},
    "filters.tas_codes": {"type": "list[string]", "description": "Treasury Account Symbol filter"},
    "filters.def_codes": {"type": "list[string]", "description": "Disaster Emergency Fund codes"},
    "filters.keywords": {"type": "list[string]", "description": "Free-text keyword search"},
    "fields": {"type": "list[string]", "description": "Human-readable field names to return", "examples": [["Award ID", "Recipient Name", "Award Amount"]]},
    "sort": {"type": "string", "description": "Sort field (human-readable)", "examples": ["Award Amount"]},
    "order": {"type": "string", "description": "asc or desc", "examples": ["desc"]},
    "limit": {"type": "int", "description": "Page size (max 100)"},
    "page": {"type": "int", "description": "Page number"},
    "subawards": {"type": "boolean", "description": "Include sub-awards"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "search.spending_by_award",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/search/spending_by_award/"],
            "methods": ["POST"],
            "query_params": SEARCH_BODY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Primary award search. POST body -- see query_params for shape.",
            "source_refs": refs,
        },
        {
            "id": "search.spending_by_category",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/search/spending_by_category/{category}/"],
            "methods": ["POST"],
            "query_params": SEARCH_BODY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Aggregate spending by category (awarding_agency, recipient, etc.).",
            "source_refs": refs,
        },
        {
            "id": "awards.single",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": ["/awards/{generated_unique_award_id}/"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Full record for a single award by unique ID.",
            "source_refs": refs,
        },
        {
            "id": "meta.references",
            "base_aliases": ["v2"],
            "base_url": BASE_URL,
            "path_templates": [p for (_, p, _) in META_ENDPOINTS],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Reference/lookup endpoints: agencies, glossary, award types, DEF codes, CFDA, filter trees. See catalog.json.references.",
            "source_refs": refs,
        },
    ]
