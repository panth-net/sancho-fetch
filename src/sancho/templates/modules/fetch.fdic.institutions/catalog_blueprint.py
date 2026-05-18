from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.fdic.institutions"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://banks.data.fdic.gov/api"
DOCS_URL = "https://banks.data.fdic.gov/docs/"


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "filters": {"type": "string", "description": "Field-level filter expression", "examples": ["STNAME:CA"]},
    "fields": {"type": "string", "description": "Comma-separated fields to return"},
    "sort_by": {"type": "string", "description": "Sort field"},
    "sort_order": {"type": "string", "description": "ASC or DESC"},
    "limit": {"type": "int", "description": "Page size (max 10,000)"},
    "offset": {"type": "int", "description": "Pagination offset"},
    "format": {"type": "string", "description": "Response format", "examples": ["json", "csv"]},
    "search": {"type": "string", "description": "Free-text search"},
    "agg_by": {"type": "string", "description": "Aggregation field"},
    "agg_sum_fields": {"type": "string", "description": "Fields to aggregate"},
}


# Three top-level data families exposed by BankFind.
RESOURCES: list[tuple[str, str, str]] = [
    ("/institutions", "institutions", "FDIC-insured depository institutions (CERT, NAME, ADDRESS, STALP, ...)"),
    ("/locations", "locations", "Branch locations -- geocoded, hierarchical (BKCLASS, UNINUM, OFFNAME, ...)"),
    ("/financials", "financials", "Quarterly call-report + UBPR financial metrics (ASSET, DEP, INCOME, ...)"),
]


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    out = []
    for path, envelope, desc in RESOURCES:
        out.append({
            "id": f"bankfind{path.replace('/', '.')}",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [path, f"{path}/{{cert}}"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "data",
            "description": desc,
            "source_refs": refs,
        })
    return out
