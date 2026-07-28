from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.hud.fmr"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://www.huduser.gov/hudapi/public"
DOCS_URL = "https://www.huduser.gov/portal/dataset/fmr-api.html"

META_LIST_STATES = "/fmr/listStates"
META_LIST_METROS = "/fmr/listMetroAreas"


FMR_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "year": {"type": "int", "description": "Fiscal year", "examples": [2024, 2025]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "fmr.data",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [
                "/fmr/data/{code}",
                "/fmr/statedata/{state}",
            ],
            "methods": ["GET"],
            "query_params": FMR_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "data",
            "description": "Fair Market Rent data for a given metro area / state / entity code. See catalog.json for valid codes.",
            "source_refs": refs,
        },
        {
            "id": "il.data",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/il/data/{code}", "/il/statedata/{state}"],
            "methods": ["GET"],
            "query_params": FMR_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "data",
            "description": "HUD Section 8 Income Limits.",
            "source_refs": refs,
        },
        {
            "id": "meta.states",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_LIST_STATES],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "All states covered by FMR. See catalog.json.states.",
            "source_refs": refs,
        },
        {
            "id": "meta.counties",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/fmr/listCounties/{state}"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Counties within a given state. See catalog.json.counties_by_state.",
            "source_refs": refs,
        },
        {
            "id": "meta.metros",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_LIST_METROS],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "All FMR metro areas (HUD HMFA + OMB CBSA).",
            "source_refs": refs,
        },
    ]
