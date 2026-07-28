from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.fda.drug_events"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.fda.gov"
DOCS_URL = "https://open.fda.gov/apis/"
DOWNLOAD_MANIFEST = "/download.json"


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "search": {"type": "string", "description": "Elasticsearch-style query", "examples": ["patient.drug.openfda.brand_name:aspirin"]},
    "count": {"type": "string", "description": "Count occurrences of a field", "examples": ["patient.reaction.reactionmeddrapt.exact"]},
    "limit": {"type": "int", "description": "Results per page (max 1000)", "examples": [10, 100, 1000]},
    "skip": {"type": "int", "description": "Pagination offset (max 25000 without key, 50000 with DATA_GOV_API_KEY)", "examples": [0, 1000]},
    "api_key": {"type": "string", "description": "api.data.gov umbrella key (raises daily rate limit)"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "drug.event",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/drug/event.json"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "FAERS adverse event reports. See catalog.json.endpoints for all other openFDA endpoints.",
            "source_refs": refs,
        },
        {
            "id": "all.endpoints",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/{category}/{endpoint}.json"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Generic openFDA query surface. Valid (category, endpoint) pairs are listed in catalog.json.endpoints (from /download.json manifest).",
            "source_refs": refs,
        },
        {
            "id": "meta.download",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [DOWNLOAD_MANIFEST],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Canonical manifest: every openFDA category + endpoint + bulk-download file list.",
            "source_refs": refs,
        },
    ]
