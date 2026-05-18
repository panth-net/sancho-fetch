from __future__ import annotations

import os
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import requests


class _FakeResponse:
    def __init__(self, payload: Any, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.headers = {"content-type": "application/json"}
        self.text = ""

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _v2_rows_for_path(path: str) -> list[dict[str, Any]]:
    if path == "/indicator":
        return [
            {"id": "SP.POP.TOTL", "name": "Population, total", "source": {"id": "2", "value": "WDI"}},
            {"id": "NY.GDP.MKTP.CD", "name": "GDP (current US$)", "source": {"id": "2", "value": "WDI"}},
        ]
    if path == "/sources":
        return [{"id": "2", "name": "World Development Indicators"}]
    if path == "/topic":
        return [{"id": "3", "value": "Economy & Growth"}]
    if path == "/country":
        return [{"id": "US", "name": "United States"}]
    if path == "/incomelevel":
        return [{"id": "HIC", "value": "High income"}]
    if path == "/lendingtype":
        return [{"id": "LNX", "value": "Not classified"}]
    if path == "/region":
        return [{"id": "NAC", "value": "North America"}]
    return []


def _fake_world_bank_get(url: str, params: dict[str, Any] | None) -> _FakeResponse | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = parsed.path
    if "api.worldbank.org" in parsed.netloc and path.startswith("/v2/"):
        collection_path = path[len("/v2") :]
        rows = _v2_rows_for_path(collection_path)
        page = 1
        if params and isinstance(params.get("page"), int):
            page = int(params["page"])
        elif "page" in query:
            page = int(query["page"][0])
        payload = [{"page": page, "pages": 1, "per_page": 20000, "total": len(rows)}, rows]
        return _FakeResponse(payload, status_code=200)

    if "search.worldbank.org" in parsed.netloc and path == "/api/v2/projects":
        payload = {
            "projects": {
                "P0001": {"id": "P0001", "project_name": "Education Improvement"},
                "P0002": {"id": "P0002", "project_name": "Health Systems"},
            }
        }
        return _FakeResponse(payload, status_code=200)

    if "ddh-openapi.worldbank.org" in parsed.netloc and path == "/datasets":
        payload = {"datasets": [{"id": "DDH-001", "name": "Sample DDH Dataset"}]}
        return _FakeResponse(payload, status_code=200)

    return None


def _nyc_catalog_results_seed() -> list[dict[str, Any]]:
    return [
        {
            "resource": {
                "id": "erm2-nwe9",
                "name": "311 Service Requests from 2020 to Present",
                "description": "NYC 311 data",
                "type": "dataset",
                "attribution": "311",
                "createdAt": "2011-10-10T05:52:20.000",
                "updatedAt": "2026-03-28T00:00:00.000",
                "metadata_updated_at": "2026-03-28T00:00:00.000",
                "data_updated_at": "2026-03-28T00:00:00.000",
                "publication_date": "2011-10-10T05:52:20.000",
                "download_count": 10,
                "page_views": {"total": 15},
                "columns_name": ["Unique Key", "Complaint Type", "Borough"],
                "columns_field_name": ["unique_key", "complaint_type", "borough"],
                "columns_datatype": ["number", "text", "text"],
                "columns_description": ["Unique row id", "Complaint", "Borough name"],
                "columns_format": [{}, {}, {}],
            },
            "classification": {
                "domain_category": "Social Services",
                "categories": ["Social Services"],
                "domain_tags": ["311"],
                "tags": ["311", "service requests"],
            },
            "metadata": {"domain": "data.cityofnewyork.us"},
            "permalink": "https://data.cityofnewyork.us/d/erm2-nwe9",
            "link": "https://data.cityofnewyork.us/resource/erm2-nwe9.json",
        },
        {
            "resource": {
                "id": "8wbx-tsch",
                "name": "For Hire Vehicles (FHV) - Active",
                "description": "Active FHV licenses",
                "type": "dataset",
                "attribution": "TLC",
                "createdAt": "2019-01-01T00:00:00.000",
                "updatedAt": "2026-03-28T00:00:00.000",
                "metadata_updated_at": "2026-03-28T00:00:00.000",
                "data_updated_at": "2026-03-28T00:00:00.000",
                "publication_date": "2019-01-01T00:00:00.000",
                "download_count": 20,
                "page_views": {"total": 25},
                "columns_name": ["License Number", "Vehicle Type"],
                "columns_field_name": ["license_number", "vehicle_type"],
                "columns_datatype": ["text", "text"],
                "columns_description": ["TLC license", "Vehicle type"],
                "columns_format": [{}, {}],
            },
            "classification": {
                "domain_category": "Transportation",
                "categories": ["Transportation"],
                "domain_tags": ["fhv"],
                "tags": ["fhv"],
            },
            "metadata": {"domain": "data.cityofnewyork.us"},
            "permalink": "https://data.cityofnewyork.us/d/8wbx-tsch",
            "link": "https://data.cityofnewyork.us/resource/8wbx-tsch.json",
        },
        {
            "resource": {
                "id": "43nn-pn8j",
                "name": "DOHMH New York City Restaurant Inspection Results",
                "description": "Restaurant inspections",
                "type": "dataset",
                "attribution": "DOHMH",
                "createdAt": "2015-01-01T00:00:00.000",
                "updatedAt": "2026-03-28T00:00:00.000",
                "metadata_updated_at": "2026-03-28T00:00:00.000",
                "data_updated_at": "2026-03-28T00:00:00.000",
                "publication_date": "2015-01-01T00:00:00.000",
                "download_count": 30,
                "page_views": {"total": 35},
                "columns_name": ["Camis", "Dba", "Boro"],
                "columns_field_name": ["camis", "dba", "boro"],
                "columns_datatype": ["number", "text", "text"],
                "columns_description": ["CAMIS", "Business name", "Borough"],
                "columns_format": [{}, {}, {}],
            },
            "classification": {
                "domain_category": "Health",
                "categories": ["Health"],
                "domain_tags": ["restaurant"],
                "tags": ["inspection", "restaurant"],
            },
            "metadata": {"domain": "data.cityofnewyork.us"},
            "permalink": "https://data.cityofnewyork.us/d/43nn-pn8j",
            "link": "https://data.cityofnewyork.us/resource/43nn-pn8j.json",
        },
    ]


def _fake_nyc_open_data_get(url: str, params: dict[str, Any] | None) -> _FakeResponse | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = parsed.path

    if parsed.netloc == "api.us.socrata.com" and path == "/api/catalog/v1":
        domain = ""
        if params and isinstance(params.get("domains"), str):
            domain = params["domains"]
        elif "domains" in query:
            domain = query["domains"][0]
        if domain != "data.cityofnewyork.us":
            return None

        limit = 1000
        offset = 0
        if params and isinstance(params.get("limit"), int):
            limit = int(params["limit"])
        elif "limit" in query:
            limit = int(query["limit"][0])
        if params and isinstance(params.get("offset"), int):
            offset = int(params["offset"])
        elif "offset" in query:
            offset = int(query["offset"][0])

        seeded = _nyc_catalog_results_seed()
        page = seeded[offset : offset + limit]
        payload = {
            "results": page,
            "resultSetSize": len(seeded),
            "timings": {"serviceMillis": 1, "searchMillis": [1, 1]},
            "warnings": [],
        }
        return _FakeResponse(payload, status_code=200)

    if parsed.netloc == "data.cityofnewyork.us" and path == "/api/views/erm2-nwe9.json":
        payload = {
            "id": "erm2-nwe9",
            "name": "311 Service Requests from 2020 to Present",
            "category": "Social Services",
            "columns": [{"id": -1, "fieldName": "unique_key"}],
        }
        return _FakeResponse(payload, status_code=200)

    if parsed.netloc == "data.cityofnewyork.us" and path == "/api/views/metadata/v1/erm2-nwe9":
        payload = {
            "id": "erm2-nwe9",
            "name": "311 Service Requests from 2020 to Present",
            "columns": [{"name": "unique_key", "dataTypeName": "number"}],
        }
        return _FakeResponse(payload, status_code=200)

    return None


@pytest.fixture(autouse=True)
def _mock_provider_discovery_network(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("SANCHO_LIVE_GATE", "").strip() == "1":
        return

    real_get = requests.get

    def fake_get(
        url: str,
        params: dict[str, Any] | None = None,
        timeout: float | int = 30,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        fake = _fake_world_bank_get(url, params)
        if fake is None:
            fake = _fake_nyc_open_data_get(url, params)
        if fake is not None:
            return fake
        return real_get(url, params=params, timeout=timeout, headers=headers, **kwargs)

    monkeypatch.setattr("requests.get", fake_get)
