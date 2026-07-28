from __future__ import annotations

from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.public_source import run_public_source


CONFIG = {'module_id': 'fetch.hrsa.hpsa', 'dataset_ref': 'usgov_hrsa_hpsa', 'default_endpoint': 'https://data.hrsa.gov/data/download?titleFilter=Shortage+Areas', 'default_params': {}, 'default_mode': 'html_links', 'default_search': 'CSV', 'default_limit': 25, 'preferred_keys': ['data', 'results', 'items']}


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    return run_public_source(context=context, payload=payload, config=CONFIG)
