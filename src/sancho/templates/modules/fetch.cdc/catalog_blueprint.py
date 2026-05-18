from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.cdc"
SCHEMA_VERSION = "1.0"

CDC_PORTAL_BASE_URL = "https://data.cdc.gov"
CDC_RESOURCE_BASE_URL = "https://data.cdc.gov/resource"

DOCS_API_ENDPOINTS = "https://dev.socrata.com/docs/endpoints"
DOCS_QUERIES = "https://dev.socrata.com/docs/queries/"
DOCS_APP_TOKENS = "https://dev.socrata.com/docs/app-tokens"
DOCS_CDC_PORTAL = "https://data.cdc.gov"


def _field(
    field_type: str,
    description: str,
    *,
    examples: list[Any] | None = None,
    required: bool = False,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": field_type,
        "required": required,
        "description": description,
        "examples": examples or [],
        "source_refs": source_refs or [],
    }


COMMON_SODA_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "$limit": _field("int", "Maximum records to return (SODA 2.0 max 50000).", examples=[100, 50000]),
    "$offset": _field("int", "Offset for pagination.", examples=[0, 50000]),
    "$select": _field("string", "SoQL select expression.", examples=["state,year,deaths"]),
    "$where": _field("string", "SoQL filter expression.", examples=["state = 'CA'"]),
    "$group": _field("string", "SoQL group-by expression.", examples=["state"]),
    "$order": _field("string", "SoQL sort expression.", examples=["year DESC"]),
    "q": _field("string", "Free-text search query.", examples=["mortality"]),
}


def _merge_params(
    primary: dict[str, dict[str, Any]],
    secondary: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    merged.update(primary)
    merged.update(secondary)
    return merged


def _family(
    family_id: str,
    *,
    base_aliases: list[str],
    base_url: str,
    path_templates: list[str],
    query_params: dict[str, dict[str, Any]],
    description: str,
    default_query_params: dict[str, Any] | None = None,
    allow_unknown_query_params: bool = False,
) -> dict[str, Any]:
    return {
        "id": family_id,
        "base_aliases": base_aliases,
        "base_url": base_url,
        "path_templates": path_templates,
        "methods": ["GET"],
        "query_params": query_params,
        "allow_unknown_query_params": allow_unknown_query_params,
        "body_fields": {},
        "allow_unknown_body_fields": False,
        "default_query_params": default_query_params or {},
        "default_body": {},
        "auth": {"method": "basic", "env_id": "SODA_API_KEY_ID", "env_secret": "SODA_API_KEY_SECRET", "required": False},
        "response_mode": "json",
        "description": description,
        "source_refs": [DOCS_CDC_PORTAL, DOCS_API_ENDPOINTS, DOCS_QUERIES, DOCS_APP_TOKENS],
    }


CURATED_DATASET_FAMILIES: list[dict[str, Any]] = [
    {
        "id": "resource.leading_death",
        "dataset_id": "bi63-dtpu",
        "description": "Leading causes of death dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "state": _field("string", "State abbreviation filter.", examples=["CA", "NY"]),
                "year": _field("string", "Year filter.", examples=["2023", "2024"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.life_expectancy",
        "dataset_id": "w9j2-ggv5",
        "description": "Life expectancy dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "year": _field("string", "Year filter.", examples=["2023"]),
                "race": _field("string", "Race filter.", examples=["All Races"]),
                "sex": _field("string", "Sex filter.", examples=["Both Sexes"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.mortality_rates",
        "dataset_id": "489q-934x",
        "description": "Quarterly mortality rates dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "year_and_quarter": _field("string", "Quarter filter.", examples=["2024-Q1"]),
                "cause_of_death": _field("string", "Cause filter.", examples=["All Causes"]),
                "rate_type": _field("string", "Rate type filter.", examples=["Crude Rate"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.places_county",
        "dataset_id": "swc5-untb",
        "description": "PLACES county-level dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "stateabbr": _field("string", "State filter.", examples=["CA"]),
                "measureid": _field("string", "Measure filter.", examples=["BPHIGH"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.places_city",
        "dataset_id": "dxpw-cm5u",
        "description": "PLACES city-level dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "stateabbr": _field("string", "State filter.", examples=["CA"]),
                "placename": _field("string", "City/place filter.", examples=["Los Angeles"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.covid_cases",
        "dataset_id": "pwn4-m3yp",
        "description": "COVID-19 cases and deaths by state profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {"state": _field("string", "State filter.", examples=["CA"])},
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.weekly_deaths",
        "dataset_id": "r8kw-7aab",
        "description": "Weekly provisional deaths profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "group": _field("string", "Grouping selector.", examples=["By Week"]),
                "state": _field("string", "State filter.", examples=["CA"]),
                "year": _field("string", "Year filter.", examples=["2024"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0, "group": "By Week"},
    },
    {
        "id": "resource.disability",
        "dataset_id": "s2qv-b27b",
        "description": "Disability prevalence dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "locationabbr": _field("string", "Location filter.", examples=["CA"]),
                "response": _field("string", "Response filter.", examples=["Yes"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.drug_overdose_state",
        "dataset_id": "xbxb-epbu",
        "description": "Drug overdose mortality dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "state": _field("string", "State filter.", examples=["CA"]),
                "year": _field("string", "Year filter.", examples=["2024"]),
                "sex": _field("string", "Sex filter.", examples=["Both Sexes"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.nutrition_obesity",
        "dataset_id": "hn4x-zwk7",
        "description": "Nutrition and obesity indicators profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "locationabbr": _field("string", "Location filter.", examples=["CA"]),
                "class": _field("string", "Class filter.", examples=["Obesity / Weight Status"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.death_rates_historical",
        "dataset_id": "6rkc-nb2q",
        "description": "Historical death rates dataset profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "leading_causes": _field("string", "Leading cause filter.", examples=["Cancer"]),
                "year": _field("string", "Year filter.", examples=["2018"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
    {
        "id": "resource.birth_indicators",
        "dataset_id": "76vv-a7x8",
        "description": "Quarterly birth indicators profile.",
        "query_params": _merge_params(
            COMMON_SODA_QUERY_PARAMS,
            {
                "topic_subgroup": _field("string", "Topic subgroup filter.", examples=["Maternal Characteristics"]),
                "race_ethnicity": _field("string", "Race/ethnicity filter.", examples=["All Races"]),
            },
        ),
        "default_query_params": {"$limit": 500, "$offset": 0},
    },
]


def build_families() -> list[dict[str, Any]]:
    families: list[dict[str, Any]] = [
        _family(
            "portal.datasets.list",
            base_aliases=["portal"],
            base_url=CDC_PORTAL_BASE_URL,
            path_templates=["/api/views"],
            query_params=_merge_params(
                {"$limit": _field("int", "Result limit.", examples=[100]), "$offset": _field("int", "Result offset.", examples=[0])},
                {"q": _field("string", "Free-text search.", examples=["mortality"])},
            ),
            allow_unknown_query_params=True,
            default_query_params={"$limit": 100, "$offset": 0},
            description="CDC Socrata dataset listing endpoint.",
        ),
    ]

    for item in CURATED_DATASET_FAMILIES:
        dataset_id = str(item["dataset_id"])
        families.append(
            _family(
                str(item["id"]),
                base_aliases=["resource"],
                base_url=CDC_RESOURCE_BASE_URL,
                path_templates=[f"/{dataset_id}.json"],
                query_params=item["query_params"],
                default_query_params=item["default_query_params"],
                description=str(item["description"]),
            )
        )

    families.append(
        _family(
            "resource.dataset_query",
            base_aliases=["resource"],
            base_url=CDC_RESOURCE_BASE_URL,
            path_templates=["/{dataset_id}.json"],
            query_params=COMMON_SODA_QUERY_PARAMS,
            allow_unknown_query_params=True,
            default_query_params={"$limit": 500, "$offset": 0},
            description="Generic CDC dataset query endpoint by Socrata dataset identifier.",
        )
    )
    return families
