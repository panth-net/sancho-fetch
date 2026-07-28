from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.nrel.alt_fuel_stations"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://developer.nrel.gov/api/alt-fuel-stations"
DOCS_URL = "https://developer.nrel.gov/docs/transportation/alt-fuel-stations-v1/"


# Known fuel-type codes (documented, not machine-enumerable).
FUEL_TYPE_CODES: list[tuple[str, str]] = [
    ("BD", "Biodiesel"),
    ("CNG", "Compressed Natural Gas"),
    ("E85", "Ethanol (E85)"),
    ("ELEC", "Electric"),
    ("HY", "Hydrogen"),
    ("LNG", "Liquefied Natural Gas"),
    ("LPG", "Propane"),
    ("RD", "Renewable Diesel"),
]

SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "api_key": {"type": "string", "description": "DATA_GOV_API_KEY"},
    "fuel_type": {"type": "string", "description": "Comma-separated fuel type codes"},
    "state": {"type": "string", "description": "State code filter"},
    "zip": {"type": "string", "description": "ZIP code filter"},
    "country": {"type": "string", "description": "Country code", "examples": ["US", "CA"]},
    "access": {"type": "string", "description": "Access type", "examples": ["public", "private"]},
    "status": {"type": "string", "description": "Station status", "examples": ["E (open)", "P (planned)", "T (temporarily closed)"]},
    "owner_type": {"type": "string", "description": "Owner category"},
    "limit": {"type": "int", "description": "Page size"},
    "offset": {"type": "int", "description": "Pagination offset"},
    "format": {"type": "string", "examples": ["json", "csv", "xml"]},
    "ev_network": {"type": "string", "description": "EV charging network (EVgo, Tesla, ChargePoint, etc.)"},
    "ev_charging_level": {"type": "string"},
    "ev_connector_type": {"type": "string"},
    "cards_accepted": {"type": "string"},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "stations.search",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/v1.json", "/v1.csv", "/v1.xml"],
            "methods": ["GET"],
            "query_params": SEARCH_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "fuel_stations",
            "description": "Primary search across ~100k+ alternative-fuel stations. See catalog.json.field_schema.",
            "source_refs": refs,
        },
        {
            "id": "stations.nearby",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/nearest.json", "/nearby-route.json"],
            "methods": ["GET"],
            "query_params": {**SEARCH_QUERY_PARAMS, "location": {"type": "string"}, "latitude": {"type": "float"}, "longitude": {"type": "float"}, "radius": {"type": "float"}},
            "response_mode": "json",
            "envelope_key": "fuel_stations",
            "description": "Nearest-by-geo search.",
            "source_refs": refs,
        },
        {
            "id": "stations.single",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/{id}.json"],
            "methods": ["GET"],
            "query_params": {"api_key": {"type": "string"}},
            "response_mode": "json",
            "envelope_key": "fuel_station",
            "description": "Single station by NREL id.",
            "source_refs": refs,
        },
    ]
