from __future__ import annotations

from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.public_source import run_public_source


CONFIG = {'module_id': 'fetch.cdc.places', 'dataset_ref': 'usgov_cdc_places', 'default_endpoint': 'https://data.cdc.gov/resource/duw2-7jbt.json', 'default_params': {'$limit': 25, 'stateabbr': 'CA', 'measure': 'Current lack of health insurance among adults aged 18-64 years'}, 'default_mode': 'json', 'default_search': None, 'default_limit': 25, 'preferred_keys': ['data', 'results', 'items']}


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    return run_public_source(context=context, payload=payload, config=CONFIG)
