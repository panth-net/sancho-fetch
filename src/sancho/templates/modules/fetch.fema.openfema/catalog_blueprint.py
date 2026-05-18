from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.fema.openfema"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://www.fema.gov/api/open"

DOCS_URL = "https://www.fema.gov/about/openfema/api"
DOCS_QUERY_PARAMS = "https://www.fema.gov/about/openfema/developer-resources"
META_DATASETS = "/v1/OpenFemaDataSets"
META_FIELDS = "/v1/OpenFemaDataSetFields"

# OpenFEMA uses OData-ish filtering across every dataset.
ODATA_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "$filter": {
        "type": "string",
        "description": "OData filter expression",
        "examples": ["state eq 'CA'", "incidentType eq 'Fire' and fyDeclared ge 2020"],
    },
    "$select": {
        "type": "string",
        "description": "Comma-separated projection of fields",
        "examples": ["disasterNumber,state,declarationDate"],
    },
    "$orderby": {
        "type": "string",
        "description": "Sort expression (field + asc|desc)",
        "examples": ["declarationDate desc"],
    },
    "$top": {"type": "int", "description": "Maximum rows to return (max 1000 per call)", "examples": [100, 1000]},
    "$skip": {"type": "int", "description": "Pagination offset", "examples": [0, 1000, 2000]},
    "$count": {"type": "string", "description": "Include total record count in response metadata", "examples": ["true"]},
    "$inlinecount": {"type": "string", "description": "Legacy alias for $count", "examples": ["allpages"]},
    "$metadata": {"type": "string", "description": "Return response metadata only", "examples": ["on", "off"]},
    "$format": {"type": "string", "description": "Response format", "examples": ["json", "jsona", "csv", "geojson"]},
    "$callback": {"type": "string", "description": "JSONP callback function name", "examples": ["myFunc"]},
}


def _family(
    family_id: str,
    *,
    base_url: str,
    path_templates: list[str],
    query_params: dict[str, dict[str, Any]],
    description: str,
    envelope_key: str,
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": family_id,
        "base_aliases": ["v1", "v2"],
        "base_url": base_url,
        "path_templates": path_templates,
        "methods": ["GET"],
        "query_params": query_params,
        "response_mode": "json",
        "envelope_key": envelope_key,
        "description": description,
        "source_refs": source_refs,
    }


def build_families() -> list[dict[str, Any]]:
    """Three top-level families: dataset metadata, field schemas, and per-dataset data.

    Per-dataset endpoints are enumerated dynamically in discovery.py after
    crawling OpenFemaDataSets.
    """
    refs = [DOCS_URL, DOCS_QUERY_PARAMS]
    return [
        _family(
            "meta.datasets",
            base_url=BASE_URL,
            path_templates=[META_DATASETS],
            query_params=ODATA_QUERY_PARAMS,
            description="Catalog of every OpenFEMA dataset with title, version, record count, distribution URLs.",
            envelope_key="OpenFemaDataSets",
            source_refs=refs,
        ),
        _family(
            "meta.fields",
            base_url=BASE_URL,
            path_templates=[META_FIELDS],
            query_params=ODATA_QUERY_PARAMS,
            description="Field schema (name, type, description) for every dataset.",
            envelope_key="OpenFemaDataSetFields",
            source_refs=refs,
        ),
        _family(
            "dataset",
            base_url=BASE_URL,
            path_templates=["/{version}/{datasetName}"],
            query_params=ODATA_QUERY_PARAMS,
            description="Actual rows for a specific dataset. See catalog.json.datasets[] for the full list of (version, name) pairs.",
            envelope_key="{datasetName}",
            source_refs=refs,
        ),
    ]
