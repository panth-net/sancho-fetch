from __future__ import annotations

from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.public_source import run_public_source


CONFIG = {
    "module_id": "fetch.cdc.heat_events",
    "dataset_ref": "usgov_cdc_heat_events",
    "default_endpoint": "https://www.cdc.gov/environmental-health-tracking/php/data-research/tracking-heat-events.html",
    "default_params": {},
    "default_mode": "html_links",
    "default_search": "data",
    "default_limit": 25,
    "preferred_keys": [
        "data",
        "results",
        "items",
        "features",
        "dataset"
    ]
}


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    return run_public_source(context=context, payload=payload, config=CONFIG)
