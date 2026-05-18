from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.sec.company_submissions"
SCHEMA_VERSION = "1.0"

# SEC serves static indexes from www.sec.gov and programmatic JSON from data.sec.gov.
BASE_URL_STATIC = "https://www.sec.gov"
BASE_URL_DATA = "https://data.sec.gov"
DOCS_URL = "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"

TICKERS_URL = "/files/company_tickers.json"
TICKERS_EXCHANGE_URL = "/files/company_tickers_exchange.json"
TICKERS_MF_URL = "/files/company_tickers_mf.json"


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "submissions",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_DATA,
            "path_templates": ["/submissions/CIK{cik10}.json"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "All filings metadata for one company. CIK is 10-digit zero-padded. filings.recent holds parallel-array tables; filings.files points to older quarters.",
            "source_refs": refs,
        },
        {
            "id": "xbrl.company_facts",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_DATA,
            "path_templates": ["/api/xbrl/companyfacts/CIK{cik10}.json"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Every reported XBRL fact for one company, grouped by taxonomy (us-gaap, dei).",
            "source_refs": refs,
        },
        {
            "id": "xbrl.company_concept",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_DATA,
            "path_templates": ["/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{concept}.json"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "A single XBRL concept across all filings for one company.",
            "source_refs": refs,
        },
        {
            "id": "xbrl.frames",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_DATA,
            "path_templates": ["/api/xbrl/frames/{taxonomy}/{concept}/{unit}/CY{year}{period}.json"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "data",
            "description": "All companies' values for one concept in one period (frame).",
            "source_refs": refs,
        },
        {
            "id": "meta.tickers",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_STATIC,
            "path_templates": [TICKERS_URL, TICKERS_EXCHANGE_URL, TICKERS_MF_URL],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "",
            "description": "Canonical company ticker indexes. See catalog.json.companies for the flattened list used to look up CIK by ticker.",
            "source_refs": refs,
        },
    ]
