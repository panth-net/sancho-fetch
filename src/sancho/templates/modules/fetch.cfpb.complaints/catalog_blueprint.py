from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.cfpb.complaints"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1"
DOCS_URL = "https://cfpb.github.io/api/ccdb/"

SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "search_term": {"type": "string", "description": "Free-text search"},
    "date_received_min": {"type": "string", "description": "Earliest complaint date (YYYY-MM-DD)"},
    "date_received_max": {"type": "string", "description": "Latest complaint date"},
    "company": {"type": "list[string]", "description": "Company name filter"},
    "company_public_response": {"type": "list[string]", "description": "Company response category"},
    "company_response": {"type": "list[string]", "description": "How company responded to consumer"},
    "consumer_consent_provided": {"type": "list[string]", "description": "Whether consumer provided consent"},
    "consumer_disputed": {"type": "list[string]", "description": "Yes/No/N/A"},
    "has_narrative": {"type": "list[string]", "description": "true/false"},
    "issue": {"type": "list[string]", "description": "Issue category (see aggregations.issue buckets)"},
    "product": {"type": "list[string]", "description": "Product category (see aggregations.product buckets)"},
    "state": {"type": "list[string]", "description": "State code"},
    "submitted_via": {"type": "list[string]", "description": "Submission channel"},
    "tags": {"type": "list[string]", "description": "Complaint tags"},
    "timely": {"type": "list[string]", "description": "Timely response Yes/No"},
    "zip_code": {"type": "list[string]", "description": "ZIP5 filter"},
    "frm": {"type": "int", "description": "Pagination offset"},
    "size": {"type": "int", "description": "Page size"},
    "sort": {"type": "string", "description": "Sort expression", "examples": ["created_date_desc", "relevance_desc"]},
    "format": {"type": "string", "description": "Response format", "examples": ["json", "csv"]},
    "no_aggs": {"type": "string", "description": "Skip aggregations for faster queries", "examples": ["true"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "search",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "hits.hits",
            "description": "Search CFPB consumer complaints (14.5M+ records). Aggregations for 12 facets returned alongside.",
            "source_refs": refs,
        },
        {
            "id": "suggest",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/_suggest"],
            "methods": ["GET"],
            "query_params": {"text": {"type": "string", "description": "Autocomplete prefix"}},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Autocomplete suggester for company names.",
            "source_refs": refs,
        },
        {
            "id": "states",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/states/"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "",
            "description": "State-level aggregation endpoint.",
            "source_refs": refs,
        },
    ]
