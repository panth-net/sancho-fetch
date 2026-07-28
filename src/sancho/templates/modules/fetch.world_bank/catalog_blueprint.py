from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.world_bank"
SCHEMA_VERSION = "1.0"

V2_BASE_URL = "https://api.worldbank.org/v2"
PROJECTS_BASE_URL = "https://search.worldbank.org/api/v2"
DDH_BASE_URL = "https://ddh-openapi.worldbank.org"

DOCS_BASE = "https://datahelpdesk.worldbank.org/knowledgebase/topics/125589-developer-information"
DOCS_BASIC = "https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures"
DOCS_PROJECTS = "https://search.worldbank.org/api/v2/projects"
DOCS_DDH = "https://ddh-openapi.worldbank.org"

COMMON_V2_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "format": {"type": "string", "description": "Response format", "examples": ["json", "xml", "jsonp", "jsonstat"]},
    "per_page": {"type": "int", "description": "Page size for list responses", "examples": [50, 1000, 32500]},
    "page": {"type": "int", "description": "Page number", "examples": [1, 2]},
    "source": {"type": "string", "description": "World Bank source database id", "examples": ["2"]},
}

DATA_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    **COMMON_V2_QUERY_PARAMS,
    "date": {"type": "string", "description": "Date range filter", "examples": ["2000:2023", "2023"]},
    "mrv": {"type": "int", "description": "Most recent values count", "examples": [1, 5]},
    "mrnev": {"type": "int", "description": "Most recent non-empty values count", "examples": [1, 3]},
    "gapfill": {"type": "string", "description": "Fill gaps by back-tracking", "examples": ["Y", "N"]},
    "frequency": {"type": "string", "description": "Frequency filter", "examples": ["Y", "Q", "M"]},
    "footnote": {"type": "string", "description": "Include footnotes", "examples": ["y"]},
    "downloadformat": {"type": "string", "description": "Download archive format", "examples": ["csv", "xml", "excel"]},
}

PROJECTS_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "format": {"type": "string", "description": "Response format", "examples": ["json"]},
    "rows": {"type": "int", "description": "Number of results", "examples": [50, 200]},
    "os": {"type": "int", "description": "Offset for pagination", "examples": [0, 50]},
    "qterm": {"type": "string", "description": "Free text query", "examples": ["education"]},
    "countrycode": {"type": "string", "description": "Country code filter", "examples": ["US", "BR"]},
    "projectstatusdisplay": {"type": "string", "description": "Project status filter", "examples": ["Active"]},
}

DDH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "page": {"type": "int", "description": "Page number", "examples": [1, 2]},
    "size": {"type": "int", "description": "Page size", "examples": [50, 200]},
    "q": {"type": "string", "description": "Search query", "examples": ["poverty"]},
}


def _family(
    family_id: str,
    *,
    base_aliases: list[str],
    base_url: str,
    path_templates: list[str],
    query_params: dict[str, dict[str, Any]],
    description: str,
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": family_id,
        "base_aliases": base_aliases,
        "base_url": base_url,
        "path_templates": path_templates,
        "methods": ["GET"],
        "query_params": query_params,
        "allow_unknown_query_params": False,
        "response_mode": "json",
        "description": description,
        "source_refs": source_refs,
    }


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_BASE, DOCS_BASIC]
    return [
        _family(
            "v2.data.country_indicator",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/country/{country}/indicator/{indicator}", "/country/{country}/indicator/{indicators}"],
            query_params=DATA_QUERY_PARAMS,
            description="World Bank v2 indicator data query family for country + indicator paths.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.indicators",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/indicator", "/indicator/{indicator}"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 indicator catalog family.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.sources",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/sources", "/sources/{source}", "/sources/{source}/indicator", "/sources/{source}/country"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 source catalog family.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.topics",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/topic", "/topic/{topic}", "/topic/{topic}/indicator"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 topic catalog family.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.countries",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/country", "/country/{country}"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 country catalog family.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.regions",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/region", "/region/{region}"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 region catalog family.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.income_levels",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/incomelevel", "/incomelevel/{incomelevel}"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 income level catalog family.",
            source_refs=refs,
        ),
        _family(
            "v2.catalog.lending_types",
            base_aliases=["v2"],
            base_url=V2_BASE_URL,
            path_templates=["/lendingtype", "/lendingtype/{lendingtype}"],
            query_params=COMMON_V2_QUERY_PARAMS,
            description="World Bank v2 lending type catalog family.",
            source_refs=refs,
        ),
        _family(
            "companion.projects.search",
            base_aliases=["projects_v2"],
            base_url=PROJECTS_BASE_URL,
            path_templates=["/projects"],
            query_params=PROJECTS_QUERY_PARAMS,
            description="World Bank Projects Search API family.",
            source_refs=[DOCS_PROJECTS],
        ),
        _family(
            "companion.ddh.datasets",
            base_aliases=["ddh"],
            base_url=DDH_BASE_URL,
            path_templates=["/datasets"],
            query_params=DDH_QUERY_PARAMS,
            description="World Bank Data Catalog (DDH) dataset listing family.",
            source_refs=[DOCS_DDH],
        ),
    ]
