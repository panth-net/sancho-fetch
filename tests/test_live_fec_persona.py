"""Persona-driven live checks for the FEC module.

These tests answer a realistic research prompt instead of checking one
endpoint at a time:

    Get me data on who was funding New Hampshire last cycle.

They intentionally walk from candidate discovery to committees, donors,
outside spending, filings, and pagination.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from _live_helpers import (
    add_and_run,
    assert_has_rows,
    assert_output_shape,
    init_workspace,
    require_env_key,
)


pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_env_key("DATA_GOV_API_KEY")
    if os.getenv("DATA_GOV_API_KEY", "").strip() == "DEMO_KEY":
        pytest.skip("FEC persona live test needs a real data.gov key; DEMO_KEY is too rate-limited.")
    tmp = tmp_path_factory.mktemp("live_fec_persona")
    return init_workspace(tmp)


def _fec(live_ws, path: str, params: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = {
        "base": "v1",
        "method": "GET",
        "path": path,
        "params": params,
    }
    payload.update(extra)
    out = add_and_run(live_ws, "fetch.fec", payload)
    assert_output_shape(out, "dataset_ref", "path", "params", "rows", "raw", "pagination")
    assert out["path"] == path
    assert isinstance(out["pagination"], dict)
    return out


def test_live_fec_new_hampshire_2024_funding_brief(live_ws):
    candidates = _fec(
        live_ws,
        "/candidates/totals/",
        {
            "cycle": 2024,
            "office": "H",
            "state": "NH",
            "sort": "-receipts",
            "per_page": 5,
        },
    )
    assert_has_rows(candidates)
    candidate = candidates["rows"][0]
    candidate_id = candidate["candidate_id"]
    assert candidate.get("state") == "NH"

    committees = _fec(
        live_ws,
        f"/candidate/{candidate_id}/committees/",
        {"cycle": 2024, "per_page": 5},
    )
    assert_has_rows(committees)

    donor_rows: list[dict[str, Any]] = []
    donor_committee_id = None
    for committee in committees["rows"]:
        committee_id = committee.get("committee_id")
        if not committee_id:
            continue
        donors = _fec(
            live_ws,
            "/schedules/schedule_a/",
            {
                "committee_id": committee_id,
                "two_year_transaction_period": 2024,
                "sort": "-contribution_receipt_amount",
                "per_page": 5,
            },
        )
        if donors["rows"]:
            donor_rows = donors["rows"]
            donor_committee_id = committee_id
            assert "usage_notice" in donors
            break

    assert donor_rows, "expected at least one itemized Schedule A donor for top NH candidate committees"
    assert donor_committee_id
    donor = donor_rows[0]
    assert "contributor_name" in donor
    assert "contribution_receipt_amount" in donor

    state_donor_rollup = _fec(
        live_ws,
        "/schedules/schedule_a/by_state/by_candidate/",
        {"candidate_id": candidate_id, "cycle": 2024, "per_page": 10},
    )
    assert isinstance(state_donor_rollup["rows"], list)

    super_pacs = _fec(
        live_ws,
        "/committees/",
        {"committee_type": "O", "cycle": 2024, "per_page": 5},
    )
    assert_has_rows(super_pacs)
    assert all(row.get("committee_type") == "O" for row in super_pacs["rows"])

    outside_spending = _fec(
        live_ws,
        "/schedules/schedule_e/",
        {
            "candidate_office_state": "NH",
            "candidate_office": "H",
            "cycle": 2024,
            "sort": "-expenditure_amount",
            "per_page": 5,
        },
    )
    assert isinstance(outside_spending["rows"], list)

    outside_by_candidate = _fec(
        live_ws,
        "/schedules/schedule_e/by_candidate/",
        {"candidate_id": candidate_id, "cycle": 2024, "per_page": 5},
    )
    assert isinstance(outside_by_candidate["rows"], list)

    filings = _fec(
        live_ws,
        "/filings/",
        {"state": "NH", "office": "H", "report_year": 2024, "per_page": 5},
    )
    assert isinstance(filings["rows"], list)

    communication_costs = _fec(
        live_ws,
        "/communication_costs/by_candidate/",
        {"candidate_id": candidate_id, "cycle": 2024, "per_page": 5},
    )
    assert isinstance(communication_costs["rows"], list)

    electioneering = _fec(
        live_ws,
        "/electioneering/by_candidate/",
        {"candidate_id": candidate_id, "cycle": 2024, "per_page": 5},
    )
    assert isinstance(electioneering["rows"], list)


def test_live_fec_bounded_super_pac_pagination(live_ws):
    out = _fec(
        live_ws,
        "/committees/",
        {"committee_type": "O", "cycle": 2024, "per_page": 2},
        pagination={"mode": "pages", "max_pages": 2},
    )
    assert_has_rows(out, min_rows=4)
    pagination = out["pagination"]
    assert pagination["mode"] == "pages"
    assert pagination["fetched_pages"] == 2
    assert pagination["fetched_rows"] >= 4
    assert pagination["stop_reason"] in {"max_pages", "complete", "max_records"}
