from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.usgs.earthquakes"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"

DOCS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/"
META_APPLICATION = "/application.json"
META_COUNT = "/count"
META_VERSION = "/version"


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "query",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/query"],
            "methods": ["GET"],
            "query_params": {
                "format": {"type": "string", "description": "Response format", "examples": ["geojson", "csv", "xml", "quakeml", "kml", "text"]},
                "starttime": {"type": "string", "description": "Event start time (ISO 8601)", "examples": ["2024-01-01"]},
                "endtime": {"type": "string", "description": "Event end time (ISO 8601)", "examples": ["2024-12-31"]},
                "minmagnitude": {"type": "float", "description": "Minimum magnitude", "examples": [4.5]},
                "maxmagnitude": {"type": "float", "description": "Maximum magnitude", "examples": [9.0]},
                "minlatitude": {"type": "float", "description": "Bounding-box south edge"},
                "maxlatitude": {"type": "float", "description": "Bounding-box north edge"},
                "minlongitude": {"type": "float", "description": "Bounding-box west edge"},
                "maxlongitude": {"type": "float", "description": "Bounding-box east edge"},
                "latitude": {"type": "float", "description": "Centre latitude for radius query"},
                "longitude": {"type": "float", "description": "Centre longitude for radius query"},
                "maxradiuskm": {"type": "float", "description": "Maximum distance from centre (km)"},
                "eventtype": {"type": "string", "description": "Event type filter", "examples": ["earthquake", "quarry blast"]},
                "catalog": {"type": "string", "description": "Catalog source", "examples": ["us", "nc", "ci"]},
                "contributor": {"type": "string", "description": "Contributor source"},
                "limit": {"type": "int", "description": "Results per request (max 20000)", "examples": [100, 20000]},
                "offset": {"type": "int", "description": "Pagination offset", "examples": [0, 20000]},
                "orderby": {"type": "string", "description": "Sort field", "examples": ["time", "time-asc", "magnitude", "magnitude-asc"]},
            },
            "response_mode": "json",
            "envelope_key": "features",
            "description": "USGS FDSN event search. See catalog.json.enums for full list of catalogs, contributors, event types, and magnitude types.",
            "source_refs": refs,
        },
        {
            "id": "count",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_COUNT],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "count",
            "description": "Plan pagination: returns the count of events that would match the filter without returning them.",
            "source_refs": refs,
        },
        {
            "id": "meta.application",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": [META_APPLICATION],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Canonical self-describing metadata: catalogs, contributors, producttypes, eventtypes, magnitudetypes, parameters.",
            "source_refs": refs,
        },
    ]
