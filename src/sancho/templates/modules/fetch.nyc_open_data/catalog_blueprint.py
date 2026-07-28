from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.nyc_open_data"
SCHEMA_VERSION = "1.0"
DOMAIN = "data.cityofnewyork.us"

DISCOVERY_BASE_URL = "https://api.us.socrata.com"
NYC_BASE_URL = f"https://{DOMAIN}"

DOCS_API_ENDPOINTS = "https://dev.socrata.com/docs/endpoints"
DOCS_QUERIES = "https://dev.socrata.com/docs/queries/"
DOCS_QUERY_OPTION = "https://dev.socrata.com/docs/queries/query"
DOCS_APP_TOKENS = "https://dev.socrata.com/docs/app-tokens"
DOCS_OPEN_DATA_PORTAL = f"https://{DOMAIN}"
DOCS_DISCOVERY_ENDPOINT = f"{DISCOVERY_BASE_URL}/api/catalog/v1"


def _field(
    field_type: str,
    description: str,
    *,
    accepted_values: list[Any] | None = None,
    examples: list[Any] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": field_type,
        "description": description,
        "accepted_values": accepted_values or [],
        "examples": examples or [],
        "source_refs": source_refs or [],
    }
    return payload


DISCOVERY_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "domains": _field(
        "string",
        "Comma-separated domain filter for catalog search.",
        examples=[DOMAIN],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "search_context": _field(
        "string",
        "Domain context for search relevance and filtering.",
        examples=[DOMAIN],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "only": _field(
        "string",
        "Resource type filter.",
        accepted_values=["datasets", "charts", "maps", "files"],
        examples=["datasets"],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "ids": _field(
        "string",
        "Comma-separated resource IDs filter.",
        examples=["erm2-nwe9"],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "q": _field(
        "string",
        "Free-text search across metadata.",
        examples=["education", "housing"],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "tags": _field(
        "string",
        "Tag filter.",
        examples=["education"],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "categories": _field(
        "string",
        "Category filter.",
        examples=["Education", "Housing & Development"],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "types": _field(
        "string",
        "Resource type selector for catalog results.",
        examples=["dataset"],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "limit": _field(
        "int",
        "Number of results per page.",
        examples=[1, 100, 1000],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
    "offset": _field(
        "int",
        "Offset into result set for pagination.",
        examples=[0, 1000],
        source_refs=[DOCS_DISCOVERY_ENDPOINT],
    ),
}

V2_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "$select": _field("string", "SoQL SELECT clause.", examples=["unique_key, complaint_type"], source_refs=[DOCS_QUERIES]),
    "$where": _field("string", "SoQL WHERE clause.", examples=["borough = 'BROOKLYN'"], source_refs=[DOCS_QUERIES]),
    "$group": _field("string", "SoQL GROUP BY clause.", examples=["borough"], source_refs=[DOCS_QUERIES]),
    "$having": _field("string", "SoQL HAVING clause.", examples=["count(*) > 10"], source_refs=[DOCS_QUERIES]),
    "$order": _field("string", "SoQL ORDER BY clause.", examples=["created_date DESC"], source_refs=[DOCS_QUERIES]),
    "$limit": _field("int", "Maximum rows to return.", examples=[100, 50000], source_refs=[DOCS_QUERIES]),
    "$offset": _field("int", "Row offset for pagination.", examples=[0, 1000], source_refs=[DOCS_QUERIES]),
    "$q": _field("string", "Full-text search query.", examples=["school"], source_refs=[DOCS_QUERIES]),
    "$query": _field(
        "string",
        "Raw SoQL statement string.",
        examples=["SELECT * WHERE borough = 'MANHATTAN' LIMIT 100"],
        source_refs=[DOCS_QUERIES, DOCS_QUERY_OPTION],
    ),
    "$$app_token": _field(
        "string",
        "Application token parameter for SODA 2.1/2.0 compatibility.",
        examples=["<token>"],
        source_refs=[DOCS_APP_TOKENS],
    ),
}

V3_QUERY_BODY_FIELDS: dict[str, dict[str, Any]] = {
    "query": _field(
        "string",
        "SoQL query string. Defaults to SELECT * if omitted by provider.",
        examples=["SELECT * LIMIT 100"],
        source_refs=[DOCS_QUERIES, DOCS_QUERY_OPTION],
    ),
    "page": _field(
        "dict",
        "Pagination object with pageNumber (1-indexed) and pageSize.",
        examples=[{"pageNumber": 1, "pageSize": 1000}],
        source_refs=[DOCS_QUERIES],
    ),
    "parameters": _field(
        "dict",
        "Parameter payload used by parameterized views when required.",
        examples=[{"parameter_name": "value"}],
        source_refs=[DOCS_QUERIES],
    ),
    "timeout": _field(
        "int",
        "Query timeout in seconds.",
        examples=[60, 600],
        source_refs=[DOCS_QUERIES],
    ),
    "includeSystem": _field(
        "bool",
        "Include system fields in v3 query response.",
        examples=[True, False],
        source_refs=[DOCS_QUERIES],
    ),
    "includeSynthetic": _field(
        "bool",
        "Include synthetic columns in v3 query response.",
        examples=[True, False],
        source_refs=[DOCS_QUERIES],
    ),
    "orderingSpecifier": _field(
        "string",
        "Ordering behavior for query/export processing.",
        accepted_values=["total", "discard"],
        examples=["total", "discard"],
        source_refs=[DOCS_QUERIES],
    ),
}

V3_EXPORT_BODY_FIELDS: dict[str, dict[str, Any]] = {
    "query": _field("string", "SoQL query for export scope.", examples=["SELECT *"], source_refs=[DOCS_QUERIES]),
    "parameters": _field(
        "dict",
        "Parameter payload used by parameterized views when required.",
        examples=[{"parameter_name": "value"}],
        source_refs=[DOCS_QUERIES],
    ),
    "timeout": _field("int", "Export timeout in seconds.", examples=[60, 600], source_refs=[DOCS_QUERIES]),
    "orderingSpecifier": _field(
        "string",
        "Ordering behavior for query/export processing.",
        accepted_values=["total", "discard"],
        examples=["total", "discard"],
        source_refs=[DOCS_QUERIES],
    ),
    "serializationOptions": _field(
        "dict",
        "Output format options, e.g. CSV separator/BOM.",
        examples=[{"separator": ",", "bom": False}],
        source_refs=[DOCS_QUERIES],
    ),
}


def _family(
    family_id: str,
    *,
    base_aliases: list[str],
    base_url: str,
    path_templates: list[str],
    methods: list[str],
    query_params: dict[str, dict[str, Any]],
    allow_unknown_query_params: bool,
    response_mode: str,
    description: str,
    source_refs: list[str],
    body_fields: dict[str, dict[str, Any]] | None = None,
    allow_unknown_body_fields: bool = False,
    auth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": family_id,
        "base_aliases": base_aliases,
        "base_url": base_url,
        "path_templates": path_templates,
        "methods": methods,
        "query_params": query_params,
        "allow_unknown_query_params": allow_unknown_query_params,
        "body_fields": body_fields or {},
        "allow_unknown_body_fields": allow_unknown_body_fields,
        "auth": auth or {},
        "response_mode": response_mode,
        "description": description,
        "source_refs": source_refs,
    }


def build_families() -> list[dict[str, Any]]:
    return [
        _family(
            "catalog.discovery.datasets",
            base_aliases=["catalog_v1"],
            base_url=DISCOVERY_BASE_URL,
            path_templates=["/api/catalog/v1"],
            methods=["GET"],
            query_params=DISCOVERY_QUERY_PARAMS,
            allow_unknown_query_params=True,
            response_mode="json",
            description="Socrata discovery search for NYC Open Data dataset catalog coverage.",
            source_refs=[DOCS_DISCOVERY_ENDPOINT, DOCS_OPEN_DATA_PORTAL],
        ),
        _family(
            "metadata.views.list",
            base_aliases=["nyc"],
            base_url=NYC_BASE_URL,
            path_templates=["/api/views.json"],
            methods=["GET"],
            query_params={
                "limit": _field("int", "Rows per page.", examples=[1, 100], source_refs=[DOCS_OPEN_DATA_PORTAL]),
                "page": _field("int", "Page number for list paging.", examples=[1, 2], source_refs=[DOCS_OPEN_DATA_PORTAL]),
                "ids": _field("string", "Resource ID filter.", examples=["erm2-nwe9"], source_refs=[DOCS_OPEN_DATA_PORTAL]),
            },
            allow_unknown_query_params=True,
            response_mode="json",
            description="NYC view listing endpoint with paging and ID filters.",
            source_refs=[DOCS_OPEN_DATA_PORTAL],
        ),
        _family(
            "metadata.views.detail",
            base_aliases=["nyc"],
            base_url=NYC_BASE_URL,
            path_templates=["/api/views/{dataset_id}.json"],
            methods=["GET"],
            query_params={},
            allow_unknown_query_params=False,
            response_mode="json",
            description="Per-view metadata document for a dataset identifier.",
            source_refs=[DOCS_OPEN_DATA_PORTAL],
        ),
        _family(
            "metadata.views.metadata_v1",
            base_aliases=["nyc"],
            base_url=NYC_BASE_URL,
            path_templates=["/api/views/metadata/v1/{dataset_id}"],
            methods=["GET"],
            query_params={},
            allow_unknown_query_params=False,
            response_mode="json",
            description="Metadata v1 view document with schema details.",
            source_refs=[DOCS_OPEN_DATA_PORTAL],
        ),
        _family(
            "soda.v2.resource",
            base_aliases=["nyc_v2"],
            base_url=NYC_BASE_URL,
            path_templates=[
                "/resource/{dataset_id}.json",
                "/resource/{dataset_id}.csv",
                "/resource/{dataset_id}.geojson",
            ],
            methods=["GET"],
            query_params=V2_QUERY_PARAMS,
            allow_unknown_query_params=True,
            response_mode="json_or_text",
            description="SODA 2.x resource endpoint for SoQL query parameters and format suffixes.",
            source_refs=[DOCS_API_ENDPOINTS, DOCS_QUERIES, DOCS_APP_TOKENS],
        ),
        _family(
            "soda.v3.query",
            base_aliases=["nyc_v3"],
            base_url=NYC_BASE_URL,
            path_templates=["/api/v3/views/{dataset_id}/query.json"],
            methods=["POST"],
            query_params={},
            allow_unknown_query_params=False,
            body_fields=V3_QUERY_BODY_FIELDS,
            allow_unknown_body_fields=True,
            auth={"method": "basic", "env_id": "SODA_API_KEY_ID", "env_secret": "SODA_API_KEY_SECRET", "required": True},
            response_mode="json",
            description="SODA 3 query endpoint. Requires application token.",
            source_refs=[DOCS_API_ENDPOINTS, DOCS_QUERIES, DOCS_APP_TOKENS],
        ),
        _family(
            "soda.v3.export",
            base_aliases=["nyc_v3"],
            base_url=NYC_BASE_URL,
            path_templates=[
                "/api/v3/views/{dataset_id}/export.csv",
                "/api/v3/views/{dataset_id}/export.json",
            ],
            methods=["POST"],
            query_params={},
            allow_unknown_query_params=False,
            body_fields=V3_EXPORT_BODY_FIELDS,
            allow_unknown_body_fields=True,
            auth={"method": "basic", "env_id": "SODA_API_KEY_ID", "env_secret": "SODA_API_KEY_SECRET", "required": True},
            response_mode="json_or_text",
            description="SODA 3 export endpoint with optional serialization options. Requires application token.",
            source_refs=[DOCS_API_ENDPOINTS, DOCS_QUERIES, DOCS_APP_TOKENS],
        ),
    ]
