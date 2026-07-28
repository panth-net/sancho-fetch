from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.clinical_trials.studies"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://clinicaltrials.gov/api/v2"

DOCS_URL = "https://clinicaltrials.gov/data-api/api"

META_STUDIES = "/studies/metadata"
META_SEARCH_AREAS = "/studies/search-areas"
META_ENUMS = "/studies/enums"
META_VERSION = "/version"
META_SIZE = "/stats/size"

SEARCH_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "query.cond": {"type": "string", "description": "Condition or disease query", "examples": ["lung cancer"]},
    "query.term": {"type": "string", "description": "Free-text query across all searchable fields", "examples": ["immunotherapy"]},
    "query.locn": {"type": "string", "description": "Location query (e.g. city, country)", "examples": ["United States"]},
    "query.titles": {"type": "string", "description": "Query restricted to study titles", "examples": ["glioblastoma"]},
    "query.intr": {"type": "string", "description": "Intervention / treatment query", "examples": ["pembrolizumab"]},
    "query.outc": {"type": "string", "description": "Outcome measure query", "examples": ["survival"]},
    "query.spons": {"type": "string", "description": "Sponsor / collaborator query", "examples": ["NIH"]},
    "query.lead": {"type": "string", "description": "Lead sponsor query", "examples": ["Pfizer"]},
    "query.id": {"type": "string", "description": "Study identifier query (NCT, other IDs)", "examples": ["NCT05000000"]},
    "query.patient": {"type": "string", "description": "Patient-centric combined query", "examples": [""]},
    "filter.overallStatus": {"type": "string", "description": "Status filter (comma-separated)", "examples": ["RECRUITING", "COMPLETED"]},
    "filter.geo": {"type": "string", "description": "Geo filter (distance/miles:lat,lng)", "examples": ["distance(40,-73,50)"]},
    "filter.ids": {"type": "string", "description": "Comma-separated NCT IDs", "examples": ["NCT01234567,NCT07654321"]},
    "filter.advanced": {"type": "string", "description": "Essie expression for advanced filtering", "examples": ["AREA[Phase]EXPAND[Term]COVER[FullMatch]PHASE3"]},
    "filter.synonyms": {"type": "string", "description": "Synonym expansion toggle", "examples": ["true", "false"]},
    "postFilter.overallStatus": {"type": "string", "description": "Post-filter status (client-side refinement)", "examples": ["ACTIVE_NOT_RECRUITING"]},
    "aggFilters": {"type": "string", "description": "Aggregate filter (kind:value)", "examples": ["phase:2", "results:with"]},
    "geoDecay": {"type": "string", "description": "Geographic relevance decay", "examples": ["func:exp,scale:100"]},
    "fields": {"type": "string", "description": "Pipe-delimited list of field names to return", "examples": ["NCTId|BriefTitle|OverallStatus"]},
    "sort": {"type": "string", "description": "Sort expression", "examples": ["LastUpdatePostDate:desc", "EnrollmentCount:asc"]},
    "countTotal": {"type": "string", "description": "Include total study count", "examples": ["true"]},
    "pageSize": {"type": "int", "description": "Results per page (max 1000)", "examples": [10, 100, 1000]},
    "pageToken": {"type": "string", "description": "Opaque cursor for the next page", "examples": [""]},
    "format": {"type": "string", "description": "Response format", "examples": ["json", "csv"]},
    "markupFormat": {"type": "string", "description": "Markup format for rich fields", "examples": ["markdown", "legacy"]},
}


def _family(
    family_id: str, *,
    path_templates: list[str],
    description: str,
    envelope_key: str,
    query_params: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": family_id,
        "base_aliases": ["v2"],
        "base_url": BASE_URL,
        "path_templates": path_templates,
        "methods": ["GET"],
        "query_params": query_params or {},
        "response_mode": "json",
        "envelope_key": envelope_key,
        "description": description,
        "source_refs": [DOCS_URL],
    }


def build_families() -> list[dict[str, Any]]:
    return [
        _family(
            "studies.search",
            path_templates=["/studies"],
            description="Search studies. Supports full Essie query language on every field. See catalog.json.metadata for the complete field tree.",
            envelope_key="studies",
            query_params=SEARCH_QUERY_PARAMS,
        ),
        _family(
            "studies.single",
            path_templates=["/studies/{nctId}"],
            description="Full record for one study by NCT ID.",
            envelope_key="",
        ),
        _family(
            "meta.studies",
            path_templates=[META_STUDIES],
            description="Recursive schema tree describing every field available on a Study record.",
            envelope_key="",
        ),
        _family(
            "meta.search_areas",
            path_templates=[META_SEARCH_AREAS],
            description="Searchable area groups (maps labels like 'BasicSearch' to their constituent fields).",
            envelope_key="",
        ),
        _family(
            "meta.enums",
            path_templates=[META_ENUMS],
            description="All enum types and allowed values (status codes, phases, sex, study types, etc.).",
            envelope_key="",
        ),
        _family(
            "meta.version",
            path_templates=[META_VERSION],
            description="Current API version and data-load timestamp.",
            envelope_key="",
        ),
        _family(
            "stats.size",
            path_templates=[META_SIZE],
            description="Size distribution statistics across all studies.",
            envelope_key="",
        ),
    ]
