from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.epa.echo_facilities"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://echodata.epa.gov/echo"
DOCS_URL = "https://echo.epa.gov/tools/web-services"

# ECHO exposes per-service REST families. Each has its own metadata endpoint
# returning the full ColumnMetadata list of every queryable field.
SERVICES: list[tuple[str, str, str]] = [
    # (service_id, metadata_path, human_name)
    ("air", "/air_rest_services.metadata", "Air Facility (Clean Air Act)"),
    ("cwa", "/cwa_rest_services.metadata", "Water (Clean Water Act / NPDES)"),
    ("rcra", "/rcra_rest_services.metadata", "Hazardous Waste (RCRA)"),
    ("sdw", "/sdw_rest_services.metadata", "Drinking Water (SDWA)"),
    ("case", "/case_rest_services.metadata", "Enforcement Case"),
    ("eff", "/eff_rest_services.metadata", "Effluent Charts"),
    ("dfr", "/dfr_rest_services.metadata", "Detailed Facility Report"),
    ("echo", "/echo_rest_services.metadata", "All-Data / cross-service"),
]


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "output": {"type": "string", "description": "Response format", "examples": ["JSON", "CSV", "GeoJSON"]},
    "p_qid": {"type": "string", "description": "Query ID (returned by get_facilities; use with get_download/get_map)"},
    "qcolumns": {"type": "string", "description": "Comma-separated column positions to include in response"},
    "responseset": {"type": "int", "description": "Page size (max 10,000 facilities)"},
    "pageno": {"type": "int", "description": "1-based page number"},
    "p_fn": {"type": "string", "description": "Facility name filter (wildcard)"},
    "p_st": {"type": "string", "description": "State code filter"},
    "p_cs": {"type": "string", "description": "City filter"},
    "p_zip": {"type": "string", "description": "ZIP code filter"},
    "p_naics": {"type": "string", "description": "NAICS code filter"},
    "p_ysl": {"type": "int", "description": "Years since last inspection"},
    "p_fy": {"type": "int", "description": "Fiscal year"},
}


def _family(svc: str, metadata_path: str, human: str) -> dict[str, Any]:
    return {
        "id": f"echo.{svc}",
        "base_aliases": ["v1"],
        "base_url": BASE_URL,
        "path_templates": [
            f"/{svc}_rest_services.get_facilities",
            f"/{svc}_rest_services.get_facility_info",
            f"/{svc}_rest_services.get_download",
            f"/{svc}_rest_services.get_map",
            f"/{svc}_rest_services.get_qid",
            metadata_path,
        ],
        "methods": ["GET", "POST"],
        "query_params": COMMON_QUERY_PARAMS,
        "response_mode": "json",
        "envelope_key": "Results",
        "description": f"ECHO {human} facility search. Column schema in catalog.json.services.{svc}.columns.",
        "source_refs": [DOCS_URL],
    }


def build_families() -> list[dict[str, Any]]:
    return [_family(svc, path, human) for (svc, path, human) in SERVICES]
