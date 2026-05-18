from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.cli_find import find_sources


def test_find_sources_census_for_black_population_query() -> None:
    candidates = find_sources("black population race census state ACS")
    ids = [c.module_id for c in candidates]
    assert any("census" in mid for mid in ids), f"Expected census in {ids[:8]}"


def test_find_sources_panama_query_returns_country_level_modules() -> None:
    candidates = find_sources("Panama country profile economy health governance")
    assert candidates, "Expected at least one candidate for the Panama query"
    country_level_hints = {
        "fetch.world_bank", "fetch.vdem", "fetch.wgi", "fetch.undp_hdr",
        "fetch.ti_cpi", "fetch.owid_charts", "fetch.owid_catalog",
        "fetch.oecd_sdmx", "fetch.un_egdi",
        # Packs are equally acceptable.
        "pack.international_core", "pack.global_governance",
        "pack.global_development", "pack.global_economic",
    }
    found = {c.module_id for c in candidates}
    assert found & country_level_hints, f"Expected country-level overlap in {found}"


def test_find_sources_returns_no_candidates_for_nonsense() -> None:
    candidates = find_sources("xyzqq_no_such_topic_zzzzz")
    assert candidates == []


def test_find_sources_surfaces_pack_public_health_for_public_health_query() -> None:
    """Packs must be ranked alongside modules; topic-level queries should hit the pack first."""
    candidates = find_sources("public health pandemic disease")
    # Top candidate for a broad public-health query must be a pack.
    assert candidates[0].kind == "pack"
    assert candidates[0].module_id == "pack.public_health"
    assert candidates[0].member_count > 0


def test_find_sources_surfaces_pack_us_housing_for_housing_query() -> None:
    candidates = find_sources("housing affordability rents metro areas")
    top_ids = [c.module_id for c in candidates[:3]]
    assert "pack.us_housing" in top_ids


def test_find_sources_pack_description_is_populated() -> None:
    candidates = find_sources("public health")
    pack = next(c for c in candidates if c.kind == "pack")
    assert pack.description
    assert "health" in pack.description.lower()


def test_cli_find_sources_json_output_says_candidates_not_plan(
    capsys: pytest.CaptureFixture,
) -> None:
    capsys.readouterr()
    rc = main(["find", "sources", "census", "ACS", "state", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "census ACS state"
    assert payload["candidate_count"] > 0
    assert "candidates" in payload["note"].lower()
    assert "selected plan" not in payload["note"].lower()
    for c in payload["candidates"]:
        # New shape exposes both `id` and back-compat `module_id` plus `kind`.
        assert "id" in c
        assert "module_id" in c
        assert "kind" in c and c["kind"] in {"pack", "module"}
        assert "score" in c
        assert "reasons" in c
