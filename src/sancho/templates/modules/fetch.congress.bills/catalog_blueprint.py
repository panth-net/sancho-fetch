from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.congress.bills"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://api.congress.gov/v3"
DOCS_URL = "https://api.congress.gov/"

# Top-level enumerable resources. Each has /{resource} list + /{resource}/{id}.
RESOURCES: list[tuple[str, str, str]] = [
    # (path, envelope_key, description)
    ("/congress", "congresses", "Congresses (118th, 117th, ...)"),
    ("/bill", "bills", "All bills (HR, S, HJRES, SJRES, ...). Very large."),
    ("/amendment", "amendments", "Amendments to bills."),
    ("/summaries", "summaries", "CRS bill summaries."),
    ("/member", "members", "All current/past members of Congress."),
    ("/committee", "committees", "House/Senate committees."),
    ("/committee-report", "reports", "Committee reports."),
    ("/committee-meeting", "committeeMeetings", "Committee meetings."),
    ("/committee-print", "committeePrints", "Committee prints."),
    ("/congressional-record", "Results.Issues", "Daily Congressional Record issues."),
    ("/nomination", "nominations", "Presidential nominations."),
    ("/treaty", "treaties", "Treaties."),
    ("/crsreport", "CRSReports", "CRS reports."),
    ("/hearing", "hearings", "Committee hearings."),
    ("/house-communication", "houseCommunications", "House communications."),
    ("/senate-communication", "senateCommunications", "Senate communications."),
    ("/bound-congressional-record", "boundCongressionalRecord", "Bound Congressional Record volumes."),
    ("/daily-congressional-record", "dailyCongressionalRecord", "Daily Congressional Record issues."),
]


COMMON_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "api_key": {"type": "string", "description": "Congress.gov API key"},
    "format": {"type": "string", "description": "Response format", "examples": ["json", "xml"]},
    "offset": {"type": "int", "description": "Pagination offset"},
    "limit": {"type": "int", "description": "Results per page (max 250)", "examples": [1, 250]},
    "fromDateTime": {"type": "string", "description": "Filter by update time (ISO 8601)"},
    "toDateTime": {"type": "string", "description": "Filter by update time"},
    "sort": {"type": "string", "description": "Sort expression", "examples": ["updateDate+desc"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    out = []
    for path, envelope, desc in RESOURCES:
        out.append({
            "id": f"resource.{path.lstrip('/').replace('-', '_').replace('/', '.')}",
            "base_aliases": ["v3"],
            "base_url": BASE_URL,
            "path_templates": [path, f"{path}/{{id}}", f"{path}/{{congress}}/{{item_type}}/{{item}}"],
            "methods": ["GET"],
            "query_params": COMMON_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": envelope,
            "description": desc,
            "source_refs": refs,
        })
    return out
