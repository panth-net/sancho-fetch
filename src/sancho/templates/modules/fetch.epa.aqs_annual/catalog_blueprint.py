from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.epa.aqs_annual"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://aqs.epa.gov/data/api"
DOCS_URL = "https://aqs.epa.gov/aqsweb/documents/data_api.html"


# Simple "list" endpoints that enumerate categorical values.
LIST_ENDPOINTS: list[tuple[str, str]] = [
    # (endpoint_path, description)
    ("list/states", "State FIPS codes and names"),
    ("list/countiesByState", "Counties (requires state= param -- walked per-state)"),
    ("list/cbsas", "Core-Based Statistical Areas"),
    ("list/classes", "Parameter classes (AQI pollutants, VOCs, etc.)"),
    ("list/pqaos", "Primary Quality Assurance Organizations"),
    ("list/mas", "Monitoring Agencies"),
    ("list/durations", "Sample durations"),
]


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "email": {"type": "string", "description": "AQS_EMAIL"},
    "key": {"type": "string", "description": "AQS_API_KEY"},
    "param": {"type": "string", "description": "Parameter code (see catalog.json.parameters_by_class)"},
    "state": {"type": "string", "description": "State FIPS (2-digit)"},
    "county": {"type": "string", "description": "County FIPS (3-digit)"},
    "site": {"type": "string", "description": "Site ID"},
    "bdate": {"type": "string", "description": "Begin date YYYYMMDD"},
    "edate": {"type": "string", "description": "End date YYYYMMDD"},
    "cbsa": {"type": "string", "description": "CBSA code"},
    "minlat": {"type": "float"}, "maxlat": {"type": "float"},
    "minlon": {"type": "float"}, "maxlon": {"type": "float"},
    "duration": {"type": "string", "description": "Sample duration"},
    "pc": {"type": "string", "description": "Parameter class"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    data_families = []
    for service in ["annualData", "dailyData", "monitors", "sampleData", "qaBlanks", "transactionsSample"]:
        data_families.append({
            "id": f"data.{service}",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [
                f"/{service}/byState", f"/{service}/byCounty", f"/{service}/bySite",
                f"/{service}/byBox", f"/{service}/byCBSA",
            ],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "Data",
            "description": f"EPA AQS {service} query. Requires email/key/param/bdate/edate/(geo) combination.",
            "source_refs": refs,
        })
    list_families = []
    for path, desc in LIST_ENDPOINTS:
        list_families.append({
            "id": f"meta.{path.replace('/', '.')}",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [f"/{path}"],
            "methods": ["GET"],
            "query_params": {k: v for k, v in COMMON_QUERY_PARAMS.items() if k in {"email", "key", "state", "pc"}},
            "response_mode": "json",
            "envelope_key": "Data",
            "description": desc,
            "source_refs": refs,
        })
    return data_families + list_families
