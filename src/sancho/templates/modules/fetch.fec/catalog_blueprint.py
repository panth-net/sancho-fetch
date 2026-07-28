from __future__ import annotations

import re
from typing import Any


PROVIDER_ID = "fetch.fec"
SCHEMA_VERSION = "1.0"

FEC_BASE_URL = "https://api.open.fec.gov/v1"

DOCS_DEVELOPERS = "https://api.open.fec.gov/developers/"
DOCS_SWAGGER = "https://api.open.fec.gov/swagger/"
CONTRIBUTOR_USAGE_URL = "https://www.fec.gov/updates/sale-or-use-contributor-information/"

SUPER_PAC_WORKFLOWS: list[dict[str, Any]] = [
    {
        "id": "super_pac_committees",
        "path": "/committees/",
        "params": {"committee_type": "O"},
        "description": "Find Super PACs, also called independent expenditure-only committees.",
    },
    {
        "id": "super_pac_donors",
        "path": "/schedules/schedule_a/",
        "description": "Itemized receipts, including donor-level contribution records.",
    },
    {
        "id": "super_pac_independent_expenditures",
        "path": "/schedules/schedule_e/",
        "description": "Independent expenditures supporting or opposing candidates.",
    },
    {
        "id": "super_pac_filings",
        "path": "/filings/",
        "description": "Official filings and report document links.",
    },
    {
        "id": "super_pac_reports",
        "path": "/committee/{committee_id}/reports/",
        "description": "Committee financial reports for a filer.",
    },
]

LEGACY_FAMILY_IDS = {
    "/candidates/search/": "v1.candidates.search",
    "/committees/": "v1.committees.search",
    "/candidate/{candidate_id}/totals/": "v1.candidates.totals",
    "/candidates/totals/": "v1.candidates.top_totals",
    "/committee/{committee_id}/totals/": "v1.committees.totals",
    "/schedules/schedule_b/": "v1.committees.disbursements",
}

DEFAULT_QUERY_PARAMS = {
    "/candidates/search/": {"q": "smith", "per_page": 20},
    "/committees/": {"q": "bank", "per_page": 20},
    "/candidate/{candidate_id}/totals/": {"cycle": 2024},
    "/candidates/totals/": {"cycle": 2024, "per_page": 20},
    "/committee/{committee_id}/totals/": {"cycle": 2024},
    "/schedules/schedule_b/": {"committee_id": "C00010603", "per_page": 20},
}

SUPER_PAC_RELEVANT_PATH_PARTS = (
    "/committees/",
    "/committee/",
    "/filings/",
    "/reports/",
    "/schedules/schedule_a",
    "/schedules/schedule_b",
    "/schedules/schedule_e",
    "/communication_costs",
    "/electioneering",
)


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text.replace("\u200b", "")).strip()
    return text


def _strip_v1(path: str) -> str:
    if path.startswith("/v1/"):
        return path[3:]
    if path == "/v1":
        return "/"
    return path


def _field_type(swagger_type: Any) -> str:
    if swagger_type == "integer":
        return "int"
    if swagger_type == "boolean":
        return "bool"
    if swagger_type == "number":
        return "number"
    if swagger_type == "array":
        return "list"
    if swagger_type == "object":
        return "dict"
    return "string"


def _field(param: dict[str, Any]) -> dict[str, Any]:
    examples: list[Any] = []
    if "default" in param:
        examples.append(param["default"])
    if "enum" in param and isinstance(param["enum"], list):
        examples.extend(param["enum"][:5])
    item: dict[str, Any] = {
        "type": _field_type(param.get("type")),
        "required": bool(param.get("required", False)),
        "description": _clean_text(param.get("description")),
        "examples": examples,
        "source_refs": [DOCS_SWAGGER],
    }
    if param.get("collectionFormat"):
        item["collection_format"] = param.get("collectionFormat")
    return item


def _query_params(operation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for param in operation.get("parameters", []):
        if not isinstance(param, dict) or param.get("in") != "query":
            continue
        name = param.get("name")
        if not isinstance(name, str) or not name or name == "api_key":
            continue
        out[name] = _field(param)
    return out


def _slug_path(path: str) -> str:
    text = path.strip("/").replace("{", "by_").replace("}", "")
    text = text.replace("/", ".").replace("-", "_")
    text = re.sub(r"[^A-Za-z0-9_.]+", "_", text)
    return text.strip("._") or "root"


def _family_id(path: str) -> str:
    return LEGACY_FAMILY_IDS.get(path, f"v1.{_slug_path(path)}")


def _description(path: str, operation: dict[str, Any]) -> str:
    summary = _clean_text(operation.get("summary"))
    description = _clean_text(operation.get("description"))
    text = summary or description or f"OpenFEC endpoint {path}."
    if _is_super_pac_relevant(path):
        text = f"{text} Relevant to Super PAC funding and spending workflows."
    return text


def _is_super_pac_relevant(path: str) -> bool:
    return any(part in path for part in SUPER_PAC_RELEVANT_PATH_PARTS)


def build_families(swagger: dict[str, Any]) -> list[dict[str, Any]]:
    families: list[dict[str, Any]] = []
    paths_obj = swagger.get("paths", {})
    if not isinstance(paths_obj, dict):
        return families

    for swagger_path in sorted(paths_obj):
        if not isinstance(swagger_path, str) or not swagger_path.startswith("/v1/"):
            continue
        methods = paths_obj.get(swagger_path)
        if not isinstance(methods, dict):
            continue
        operation = methods.get("get")
        if not isinstance(operation, dict):
            continue
        produces = operation.get("produces") or swagger.get("produces") or ["application/json"]
        if isinstance(produces, list) and not any("json" in str(item) for item in produces):
            continue

        path = _strip_v1(swagger_path)
        family = {
            "id": _family_id(path),
            "base_aliases": ["v1"],
            "base_url": FEC_BASE_URL,
            "path_templates": [path],
            "methods": ["GET"],
            "query_params": _query_params(operation),
            "allow_unknown_query_params": True,
            "body_fields": {},
            "allow_unknown_body_fields": False,
            "default_query_params": DEFAULT_QUERY_PARAMS.get(path, {}),
            "default_body": {},
            "auth": {"query": {"api_key": "DATA_GOV_API_KEY"}, "required": True},
            "response_mode": "json",
            "description": _description(path, operation),
            "source_refs": [DOCS_DEVELOPERS, DOCS_SWAGGER],
            "tags": operation.get("tags", []),
            "super_pac_relevant": _is_super_pac_relevant(path),
        }
        families.append(family)
    return families
