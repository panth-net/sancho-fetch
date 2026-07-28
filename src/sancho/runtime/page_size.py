from __future__ import annotations

from collections.abc import Iterable
from typing import Any


SOCRATA_MAX_LIMIT = 50_000
WORLD_BANK_MAX_PER_PAGE = 32_500


_DEFAULTS: dict[str, dict[str, Any]] = {
    "fetch.cfpb.complaints": {"size": 1_000},
    "fetch.clinical_trials.studies": {"pageSize": 1_000},
    "fetch.college_scorecard.schools": {"per_page": 100},
    "fetch.congress.bills": {"limit": 250},
    "fetch.dc_open_data": {"resultRecordCount": 1_000},
    "fetch.doj.press_releases": {"pagesize": 50},
    "fetch.dol.osha_inspections": {"limit": 10_000},
    "fetch.eia.series": {"length": 5_000},
    "fetch.fda.drug_events": {"limit": 1_000},
    "fetch.fdic.institutions": {"limit": 10_000},
    "fetch.federal_register.documents": {"per_page": 1_000},
    "fetch.fema.openfema": {"$top": 10_000},
    "fetch.noaa.cdo": {"limit": 1_000},
    "fetch.regulations.dockets": {"page[size]": 250},
    "fetch.treasury.fiscal_data": {"page[size]": 10_000},
    "fetch.usda.fooddata_search": {"pageSize": 200},
    "fetch.usgs.earthquakes": {"limit": 20_000},
}

_DKAN_MODULES = {
    "fetch.cms.data",
    "fetch.cms.medicaid",
    "fetch.open_payments.datasets",
}

_SOCRATA_MODULES = {
    "fetch.socrata.chicago_crimes",
    "fetch.socrata.la_crime",
    "fetch.socrata.seattle_building_permits",
    "fetch.socrata.sf_building_permits",
}


def _explicit_set(explicit_keys: Iterable[str] | None) -> set[str]:
    if explicit_keys is None:
        return set()
    return {str(key) for key in explicit_keys}


def _set_default(
    params: dict[str, Any],
    key: str,
    value: Any,
    explicit_keys: set[str],
) -> None:
    if key in explicit_keys:
        return
    params[key] = value


def _family_query_params(family: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(family, dict):
        return {}
    spec = family.get("query_params", {})
    return spec if isinstance(spec, dict) else {}


def _endpoint_contains(endpoint: str | None, needles: Iterable[str]) -> bool:
    if not endpoint:
        return False
    lowered = endpoint.lower()
    return any(needle.lower() in lowered for needle in needles)


def apply_max_page_size(
    params: dict[str, Any],
    *,
    module_id: str,
    endpoint: str | None = None,
    family: dict[str, Any] | None = None,
    base: str | None = None,
    explicit_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Apply provider-documented maximum page-size defaults.

    Explicit caller values always win. This helper is intentionally small and
    only covers providers where the repo has a known pagination field and a
    documented or live-verified maximum.
    """
    effective = dict(params)
    explicit = _explicit_set(explicit_keys)

    if module_id == "fetch.world_bank":
        query_spec = _family_query_params(family)
        if base == "v2" or "per_page" in query_spec:
            _set_default(effective, "format", "json", explicit)
            _set_default(effective, "per_page", WORLD_BANK_MAX_PER_PAGE, explicit)
        return effective

    if module_id == "fetch.cdc":
        if "$limit" in _family_query_params(family):
            _set_default(effective, "$limit", SOCRATA_MAX_LIMIT, explicit)
        return effective

    if module_id == "fetch.nyc_open_data":
        if "$limit" in _family_query_params(family):
            _set_default(effective, "$limit", SOCRATA_MAX_LIMIT, explicit)
        return effective

    if module_id in _SOCRATA_MODULES:
        _set_default(effective, "$limit", SOCRATA_MAX_LIMIT, explicit)
        return effective

    if module_id in _DKAN_MODULES:
        if _endpoint_contains(endpoint, ("/datastore/", "/api/1/search")):
            _set_default(effective, "limit", 500, explicit)
        return effective

    if module_id == "fetch.nrel.alt_fuel_stations":
        if _endpoint_contains(
            endpoint,
            ("/v1.json", "/nearest", "/nearby-route", "/ev-charging-units"),
        ):
            _set_default(effective, "limit", "all", explicit)
        return effective

    for key, value in _DEFAULTS.get(module_id, {}).items():
        _set_default(effective, key, value, explicit)
    return effective
