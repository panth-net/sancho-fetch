from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.iati"
SCHEMA_VERSION = "1.0"

BASE_URL = "https://codelists.codeforiati.org/api/json/en"
DATASTORE_BASE_URL = "https://api.iatistandard.org/datastore"
DOCS_URL = "https://iatistandard.org/en/guidance/developer/codelist-api/"

# Complete list of IATI Standard codelists (CLv3 JSON). Every name maps to
# a URL at {BASE_URL}/{name}.json.
CODELIST_NAMES: list[str] = [
    "ActivityDateType", "ActivityScope", "ActivityStatus", "AidType",
    "AidType-category", "AidTypeVocabulary", "BudgetIdentifier",
    "BudgetIdentifierSector", "BudgetIdentifierSector-category",
    "BudgetIdentifierVocabulary", "BudgetNotProvided", "BudgetStatus",
    "BudgetType", "CRSAddOtherFlags", "CRSChannelCode",
    "CashandVoucherModalities", "CollaborationType", "ConditionType",
    "ContactType", "Country", "Currency", "DescriptionType",
    "DisbursementChannel", "DocumentCategory", "DocumentCategory-category",
    "EarmarkingCategory", "FileFormat", "FinanceType",
    "FinanceType-category", "FlowType", "GazetteerAgency",
    "GeographicExactness", "GeographicLocationClass",
    "GeographicLocationReach", "GeographicVocabulary",
    "GeographicalPrecision", "HumanitarianScopeType",
    "HumanitarianScopeVocabulary", "IATIOrganisationIdentifier",
    "IndicatorMeasure", "IndicatorVocabulary", "Language",
    "LoanRepaymentPeriod", "LoanRepaymentType", "LocationType",
    "LocationType-category", "OrganisationIdentifier",
    "OrganisationRegistrationAgency", "OrganisationRole",
    "OrganisationType", "OtherIdentifierType", "PolicyMarker",
    "PolicyMarkerVocabulary", "PolicySignificance", "PublisherType",
    "Region", "RegionVocabulary", "RelatedActivityType", "ResultType",
    "ResultVocabulary", "Sector", "SectorCategory", "SectorVocabulary",
    "TagVocabulary", "TiedStatus", "TransactionType", "UNSDG-Goals",
    "UNSDG-Targets", "VerificationStatus", "Version", "Vocabulary",
]


DATASTORE_SEARCH_PARAMS: dict[str, dict[str, Any]] = {
    "q": {"type": "string", "description": "Solr query expression"},
    "fl": {"type": "string", "description": "Fields to return (comma-separated)"},
    "fq": {"type": "list[string]", "description": "Filter queries"},
    "sort": {"type": "string", "description": "Sort expression"},
    "start": {"type": "int", "description": "Result offset"},
    "rows": {"type": "int", "description": "Results per page"},
    "facet": {"type": "string", "description": "Enable faceting", "examples": ["true"]},
    "facet.field": {"type": "list[string]", "description": "Facet fields"},
    "wt": {"type": "string", "description": "Response format", "examples": ["json", "xml", "csv"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "codelist",
            "base_aliases": ["v1"],
            "base_url": BASE_URL,
            "path_templates": ["/{codelist_name}.json", "/{codelist_name}.xml", "/{codelist_name}.csv"],
            "methods": ["GET"],
            "query_params": {},
            "response_mode": "json",
            "envelope_key": "data",
            "description": "A single IATI codelist (Sector, Country, AidType, etc.). Valid codelist names are listed in catalog.json.codelists.",
            "source_refs": refs,
        },
        {
            "id": "datastore.activity",
            "base_aliases": ["v3"],
            "base_url": DATASTORE_BASE_URL,
            "path_templates": ["/activity/select", "/activity/iati"],
            "methods": ["GET"],
            "query_params": DATASTORE_SEARCH_PARAMS,
            "response_mode": "json",
            "envelope_key": "response.docs",
            "description": "IATI Datastore -- Solr-backed search over all IATI activities.",
            "source_refs": refs,
        },
        {
            "id": "datastore.budget",
            "base_aliases": ["v3"],
            "base_url": DATASTORE_BASE_URL,
            "path_templates": ["/budget/select"],
            "methods": ["GET"],
            "query_params": DATASTORE_SEARCH_PARAMS,
            "response_mode": "json",
            "envelope_key": "response.docs",
            "description": "IATI Datastore -- budget-level records.",
            "source_refs": refs,
        },
        {
            "id": "datastore.transaction",
            "base_aliases": ["v3"],
            "base_url": DATASTORE_BASE_URL,
            "path_templates": ["/transaction/select"],
            "methods": ["GET"],
            "query_params": DATASTORE_SEARCH_PARAMS,
            "response_mode": "json",
            "envelope_key": "response.docs",
            "description": "IATI Datastore -- transaction-level records.",
            "source_refs": refs,
        },
    ]
