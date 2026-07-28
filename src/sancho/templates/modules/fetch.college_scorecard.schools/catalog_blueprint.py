from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.college_scorecard.schools"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.data.gov/ed/collegescorecard/v1"
DOCS_URL = "https://collegescorecard.ed.gov/data/api-documentation"


SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "api_key": {"type": "string", "description": "DATA_GOV_API_KEY"},
    "fields": {"type": "string", "description": "Comma-separated fields to return (use dotted paths like latest.admissions.admission_rate.overall)"},
    "per_page": {"type": "int", "description": "Page size (max 100)"},
    "page": {"type": "int", "description": "0-based page number"},
    "sort": {"type": "string", "description": "Sort expression", "examples": ["latest.student.size:desc"]},
    "school.name": {"type": "string", "description": "School name filter (partial match)"},
    "school.state": {"type": "string", "description": "State code"},
    "school.zip": {"type": "string", "description": "ZIP code"},
    "school.carnegie_basic": {"type": "int", "description": "Carnegie Classification"},
    "school.ownership": {"type": "int", "description": "1=Public, 2=Private non-profit, 3=Private for-profit"},
    "school.degrees_awarded.predominant": {"type": "int", "description": "Predominant degree awarded"},
    "latest.student.size__range": {"type": "string", "description": "Enrollment size range"},
    "latest.admissions.admission_rate.overall__range": {"type": "string", "description": "Admission rate range"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "schools",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/schools", "/schools.csv"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Search/list schools. 6,000+ institutions. See catalog.json.sample_school for the full field hierarchy (deeply nested: school.*, latest.*, YYYY.*).",
            "source_refs": refs,
        },
    ]
