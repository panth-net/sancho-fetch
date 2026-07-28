"""Live checks for public health convenience modules.

Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_health_public.py -v
"""

from __future__ import annotations

import pytest

from _live_helpers import add_and_run, assert_has_rows, init_workspace, require_live_gate

pytestmark = pytest.mark.live


PUBLIC_HEALTH_MODULES = [
    "fetch.ahrq.nhqdr",
    "fetch.ahrq.sdoh",
    "fetch.atsdr.eji",
    "fetch.cdc.biomonitoring",
    "fetch.cdc.birth_defects",
    "fetch.cdc.heat_events",
    "fetch.cdc.mmwr",
    "fetch.cdc.nsfg",
    "fetch.cdc.nvss",
    "fetch.cdc.nwss",
    "fetch.cdc.places",
    "fetch.cdc.ssun",
    "fetch.cdc.tracking",
    "fetch.cdc.vaxview",
    "fetch.cdc.wisqars",
    "fetch.cdc.wonder",
    "fetch.cejst",
    "fetch.census.cps",
    "fetch.census.onthemap_em",
    "fetch.census.sipp",
    "fetch.cms.cciio",
    "fetch.cms.marketplace_reports",
    "fetch.cms.synpuf",
    "fetch.dol.naws",
    "fetch.ed.crdc",
    "fetch.epa.ejscreen",
    "fetch.epa.enviroatlas",
    "fetch.epa.iris",
    "fetch.epa.smart_location",
    "fetch.fema.nri",
    "fetch.hhs.poverty_guidelines",
    "fetch.hrsa.ahrf",
    "fetch.hrsa.hpsa",
    "fetch.hrsa.nsch",
    "fetch.hrsa.uds",
    "fetch.hud.hdx_homelessness",
    "fetch.noaa.cmra",
    "fetch.umich.nanda",
    "fetch.usda.food_access",
    "fetch.usda.food_security",
]


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_live_gate()
    tmp = tmp_path_factory.mktemp("live_health_public")
    return init_workspace(tmp)


@pytest.mark.parametrize("module_id", PUBLIC_HEALTH_MODULES, ids=PUBLIC_HEALTH_MODULES)
def test_live_public_health_source_defaults(live_ws, module_id: str):
    out = add_and_run(live_ws, module_id, {"limit": 5})
    assert out["dataset_ref"]
    assert out["endpoint"]
    assert_has_rows(out)
