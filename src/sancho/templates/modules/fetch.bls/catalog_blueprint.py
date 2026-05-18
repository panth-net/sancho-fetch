from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.bls"
SCHEMA_VERSION = "1.0"

V2_BASE_URL = "https://api.bls.gov/publicAPI/v2"

DOCS_HOME = "https://www.bls.gov/developers/home.htm"
DOCS_SIGNATURE = "https://www.bls.gov/developers/api_signature_v2.htm"


def _field(
    field_type: str,
    description: str,
    *,
    required: bool = False,
    examples: list[Any] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": field_type,
        "required": required,
        "description": description,
        "examples": examples or [],
        "source_refs": source_refs or [],
    }


TIMESERIES_BODY_FIELDS: dict[str, dict[str, Any]] = {
    "seriesid": _field(
        "list",
        "Series identifiers list (max 50).",
        required=True,
        examples=[["CUUR0000SA0"]],
        source_refs=[DOCS_SIGNATURE],
    ),
    "startyear": _field(
        "string",
        "Start year for observations.",
        examples=["2020", "2023"],
        source_refs=[DOCS_SIGNATURE],
    ),
    "endyear": _field(
        "string",
        "End year for observations.",
        examples=["2024"],
        source_refs=[DOCS_SIGNATURE],
    ),
    "catalog": _field(
        "bool",
        "Include catalog metadata.",
        examples=[True, False],
        source_refs=[DOCS_SIGNATURE],
    ),
    "calculations": _field(
        "bool",
        "Include calculations payload.",
        examples=[True, False],
        source_refs=[DOCS_SIGNATURE],
    ),
    "annualaverage": _field(
        "bool",
        "Include annual average values.",
        examples=[True, False],
        source_refs=[DOCS_SIGNATURE],
    ),
    "aspects": _field(
        "bool",
        "Include additional aspects in result.",
        examples=[True, False],
        source_refs=[DOCS_SIGNATURE],
    ),
    "latest": _field(
        "bool",
        "Return most recent values only.",
        examples=[True, False],
        source_refs=[DOCS_SIGNATURE],
    ),
}


def _family(
    family_id: str,
    *,
    base_aliases: list[str],
    path_templates: list[str],
    methods: list[str],
    description: str,
    query_params: dict[str, dict[str, Any]] | None = None,
    body_fields: dict[str, dict[str, Any]] | None = None,
    default_query_params: dict[str, Any] | None = None,
    default_body: dict[str, Any] | None = None,
    auth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": family_id,
        "base_aliases": base_aliases,
        "base_url": V2_BASE_URL,
        "path_templates": path_templates,
        "methods": methods,
        "query_params": query_params or {},
        "allow_unknown_query_params": False,
        "body_fields": body_fields or {},
        "allow_unknown_body_fields": False,
        "default_query_params": default_query_params or {},
        "default_body": default_body or {},
        "auth": auth or {},
        "response_mode": "json",
        "description": description,
        "source_refs": [DOCS_HOME, DOCS_SIGNATURE],
    }


def build_families() -> list[dict[str, Any]]:
    return [
        _family(
            "v2.timeseries.data",
            base_aliases=["v2"],
            path_templates=["/timeseries/data/", "/timeseries/data"],
            methods=["POST"],
            body_fields=TIMESERIES_BODY_FIELDS,
            default_body={
                "seriesid": ["CUUR0000SA0"],
                "startyear": "2023",
                "endyear": "2024",
                "calculations": False,
                "annualaverage": False,
            },
            auth={"body": {"registrationkey": "BLS_API_KEY"}, "required": False},
            description="Primary BLS time series data family.",
        ),
        _family(
            "v2.timeseries.latest",
            base_aliases=["v2_latest"],
            path_templates=["/timeseries/data/", "/timeseries/data"],
            methods=["POST"],
            body_fields=TIMESERIES_BODY_FIELDS,
            default_body={
                "seriesid": ["CUUR0000SA0"],
                "latest": True,
            },
            auth={"body": {"registrationkey": "BLS_API_KEY"}, "required": False},
            description="Latest-value convenience profile for BLS time series data.",
        ),
        _family(
            "v2.timeseries.cpi_components",
            base_aliases=["v2_cpi_components"],
            path_templates=["/timeseries/data/", "/timeseries/data"],
            methods=["POST"],
            body_fields=TIMESERIES_BODY_FIELDS,
            default_body={
                "seriesid": [
                    "CUUR0000SA0",
                    "CUUR0000SA0L1E",
                    "CUUR0000SAF1",
                    "CUUR0000SAH1",
                    "CUUR0000SETB01",
                ],
                "startyear": "2020",
                "endyear": "2024",
            },
            auth={"body": {"registrationkey": "BLS_API_KEY"}, "required": False},
            description="Curated CPI component profile over the BLS time series family.",
        ),
        _family(
            "v2.timeseries.state_employment",
            base_aliases=["v2_state_employment"],
            path_templates=["/timeseries/data/", "/timeseries/data"],
            methods=["POST"],
            body_fields=TIMESERIES_BODY_FIELDS,
            default_body={
                "seriesid": [
                    "LASST060000000000003",
                    "LASST060000000000005",
                    "LASST060000000000006",
                ],
                "startyear": "2020",
                "endyear": "2024",
            },
            auth={"body": {"registrationkey": "BLS_API_KEY"}, "required": False},
            description="Curated state employment profile over the BLS time series family.",
        ),
        _family(
            "v2.surveys.list",
            base_aliases=["v2"],
            path_templates=["/surveys", "/surveys/"],
            methods=["GET"],
            query_params={},
            description="BLS survey metadata list family.",
        ),
    ]
