from __future__ import annotations

from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.public_source import run_public_source


CONFIG = {'module_id': 'fetch.fema.nri', 'dataset_ref': 'usgov_fema_nri', 'default_endpoint': 'https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Census_Tracts/FeatureServer/0/query', 'default_params': {'f': 'json', 'where': "STATEABBRV='CA'", 'outFields': 'STATEABBRV,COUNTY,TRACT,RISK_SCORE,RISK_RATNG', 'resultRecordCount': 25, 'returnGeometry': 'false'}, 'default_mode': 'json', 'default_search': None, 'default_limit': 25, 'preferred_keys': ['features']}


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    return run_public_source(context=context, payload=payload, config=CONFIG)
