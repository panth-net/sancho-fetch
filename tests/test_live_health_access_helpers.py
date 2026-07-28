"""Live checks for public reference/access helpers.

Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_health_access_helpers.py -v
"""

from __future__ import annotations

import pytest

from _live_helpers import add_and_run, assert_has_rows, init_workspace, require_live_gate

pytestmark = pytest.mark.live


ACCESS_HELPERS = [
    "fetch.nih.usrds",
    "fetch.nlm.vsac",
]


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_live_gate()
    tmp = tmp_path_factory.mktemp("live_health_access_helpers")
    return init_workspace(tmp)


@pytest.mark.parametrize("module_id", ACCESS_HELPERS, ids=ACCESS_HELPERS)
def test_live_access_helper(live_ws, module_id: str):
    out = add_and_run(live_ws, module_id, {"limit": 5})
    assert out["dataset_ref"]
    assert out["mode"] == "html_links"
    assert_has_rows(out)
    assert all("url" in row for row in out["rows"])
