from __future__ import annotations

from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.public_source import run_public_source


CONFIG = {
    "module_id": "fetch.hhs.poverty_guidelines",
    "dataset_ref": "usgov_hhs_poverty_guidelines",
    "default_endpoint": "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines",
    "default_params": {},
    "default_mode": "html_links",
    "default_search": "poverty",
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
