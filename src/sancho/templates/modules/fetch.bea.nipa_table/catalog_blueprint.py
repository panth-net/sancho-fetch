from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.bea.nipa_table"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://apps.bea.gov/api/data"
DOCS_URL = "https://apps.bea.gov/API/signup/"


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "UserID": {"type": "string", "description": "BEA API key (env: BEA_API_KEY)"},
    "method": {"type": "string", "description": "API method", "examples": ["GetData", "GetParameterList", "GetParameterValues", "GetDataSetList"]},
    "DataSetName": {"type": "string", "description": "Target dataset", "examples": ["NIPA", "NIUnderlyingDetail", "Regional", "ITA", "FixedAssets", "IIP"]},
    "ResultFormat": {"type": "string", "description": "Response format", "examples": ["JSON", "XML"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "data",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/"],
            "methods": ["GET"],
            "query_params": {
                **COMMON_QUERY_PARAMS,
                "TableName": {"type": "string", "description": "NIPA/FixedAssets table name", "examples": ["T10101"]},
                "Frequency": {"type": "string", "description": "A (annual), Q (quarterly), M (monthly)"},
                "Year": {"type": "string", "description": "Year(s) -- comma-separated or 'ALL'", "examples": ["ALL", "2020,2021"]},
                "LineNumber": {"type": "int", "description": "Table line number"},
                "GeoFips": {"type": "string", "description": "Regional geo-FIPS code"},
                "TypeOfInvestment": {"type": "string"},
                "DirectionOfInvestment": {"type": "string"},
            },
            "response_mode": "json",
            "envelope_key": "BEAAPI.Results.Data",
            "description": "Fetch data rows. See catalog.json.datasets[] for per-dataset parameter requirements.",
            "source_refs": refs,
        },
        {
            "id": "meta.datasets",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/"],
            "methods": ["GET"],
            "query_params": {**COMMON_QUERY_PARAMS, "method": {"type": "string", "examples": ["GetDataSetList"]}},
            "response_mode": "json",
            "envelope_key": "BEAAPI.Results.Dataset",
            "description": "List all BEA datasets (13 as of 2025).",
            "source_refs": refs,
        },
        {
            "id": "meta.parameters",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/"],
            "methods": ["GET"],
            "query_params": {**COMMON_QUERY_PARAMS, "method": {"type": "string", "examples": ["GetParameterList"]}, "DataSetName": {"type": "string"}},
            "response_mode": "json",
            "envelope_key": "BEAAPI.Results.Parameter",
            "description": "List parameters + their required/optional flags for one dataset.",
            "source_refs": refs,
        },
        {
            "id": "meta.parameter_values",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/"],
            "methods": ["GET"],
            "query_params": {**COMMON_QUERY_PARAMS, "method": {"type": "string", "examples": ["GetParameterValues"]}, "ParameterName": {"type": "string"}},
            "response_mode": "json",
            "envelope_key": "BEAAPI.Results.ParamValue",
            "description": "List allowed values for a given parameter. Call per dataset+parameter pair.",
            "source_refs": refs,
        },
    ]
