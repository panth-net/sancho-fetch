from __future__ import annotations

from pathlib import Path
from typing import Any

ZERO_KEY_PROVIDERS: dict[str, dict[str, Any]] = {
    "world_bank": {
        "shape": "catalog",
        "base": "v2",
        "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
        "params": {"format": "json", "per_page": 10, "date": "2022"},
        "description": "World population by country (2022), World Bank WDI",
    },
    "usgs.earthquakes": {
        "shape": "endpoint",
        "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
        "params": {"format": "geojson", "limit": 10, "orderby": "time"},
        "description": "10 most recent USGS earthquakes",
    },
    "treasury.fiscal_data": {
        "shape": "endpoint",
        "endpoint": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
        "params": {"sort": "-record_date", "page[size]": 5},
        "description": "Most recent US federal debt snapshots, Treasury Fiscal Data",
    },
    "federal_register.documents": {
        "shape": "endpoint",
        "endpoint": "https://www.federalregister.gov/api/v1/documents.json",
        "params": {"per_page": 10, "order": "newest"},
        "description": "10 most recent Federal Register documents",
    },
    "fema.openfema": {
        "shape": "endpoint",
        "endpoint": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
        "params": {"$top": 10, "$orderby": "declarationDate desc"},
        "description": "10 most recent FEMA disaster declarations",
    },
}


def supported_providers() -> list[str]:
    return sorted(ZERO_KEY_PROVIDERS.keys())


def _rel_workspace(ws: Path) -> str:
    try:
        rel = ws.relative_to(Path.cwd())
        return str(rel) if str(rel) != "." else "."
    except ValueError:
        return str(ws)


def format_next_steps_after_init(workspace_root: Path) -> str:
    ws = _rel_workspace(workspace_root)
    return (
        "\n"
        "Next: pull your first dataset (no API key needed):\n"
        f"  sancho fetch sample world_bank --workspace {ws}\n"
        "\n"
        "Then explore:\n"
        "  sancho inventory   # see every built-in pack and fetch provider\n"
        f"  sancho fetch catalog world_bank --workspace {ws}   # see all endpoints\n"
        f"  sancho add pack.global_economic --workspace {ws}   # install a starter pack\n"
    )


def format_next_steps_after_doctor(workspace_root: Path) -> str:
    ws = _rel_workspace(workspace_root)
    return (
        "\n"
        f"Next: sancho fetch sample world_bank --workspace {ws}\n"
    )
