from __future__ import annotations

from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.public_source import run_public_source


CONFIG = {'module_id': 'fetch.nih.usrds', 'dataset_ref': 'usgov_nih_usrds', 'default_endpoint': 'https://usrds-adr.niddk.nih.gov/2025', 'default_params': {}, 'default_mode': 'html_links', 'default_search': 'download', 'default_limit': 25, 'preferred_keys': ['data', 'results', 'items', 'features', 'dataset']}


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    return run_public_source(context=context, payload=payload, config=CONFIG)
