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


def test_find_sources_matches_whole_words_not_substrings() -> None:
    # "population of Brazil over time": "over" must not substring-match
    # 'gOVERnance', 'pOVERty', or 'OVERture', and the canonical population
    # source must surface on the concept word alone.
    candidates = find_sources("population of Brazil over time")
    ids = [c.module_id for c in candidates]
    assert "fetch.world_bank" in ids, f"Expected world_bank in {ids[:8]}"
    reasons = [r for c in candidates for r in c.reasons]
    assert not any("'over'" in r for r in reasons), f"'over' scored: {reasons}"


def test_find_sources_golden_queries_rank_the_canonical_module() -> None:
    # The queries a first-time user actually types. Each canonical module must
    # appear in the top 5 -- these pin the concept-led description audit.
    golden = {
        "unemployment rate over time": "fetch.bls",
        "inflation consumer prices": "fetch.fred.series",
        "hurricane disaster declarations": "fetch.fema.openfema",
        "weather forecast alerts": "fetch.noaa.nws",
        "national debt government spending": "fetch.treasury.fiscal_data",
        "electricity and gasoline prices": "fetch.eia.series",
        "european unemployment statistics": "fetch.eurostat",
        "drug recalls adverse events": "fetch.fda.drug_events",
    }
    for query, expected in golden.items():
        top5 = [c.module_id for c in find_sources(query)[:5]]
        assert expected in top5, f"{query!r}: expected {expected} in {top5}"


def test_find_sources_reports_coverage_from_manifest() -> None:
    candidates = find_sources("world bank population indicators")
    by_id = {c.module_id: c for c in candidates}
    assert by_id["fetch.world_bank"].coverage == "global"


def test_find_sources_word_boundary_allows_plural_and_id_separators() -> None:
    from sancho.cli_find import _term_hit

    assert _term_hit("bank", "fetch.world_bank")  # '_' is a separator
    assert _term_hit("recall", "fetch.nhtsa.recalls")  # singular matches plural
    assert not _term_hit("over", "global governance modules")
    assert not _term_hit("age", "percentage of income")


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


def _write_custom_module(
    workspace_root: Path,
    *,
    module_id: str = "fetch.custom.dc_bike_lanes",
    dirname: str = "dc_bike_lanes",
    description: str = "Protected bike lane centerlines from the Washington DC open data portal",
) -> None:
    module_dir = workspace_root / "custom" / "fetch" / dirname
    module_dir.mkdir(parents=True)
    (module_dir / "module.yaml").write_text(
        "\n".join(
            [
                f"id: {module_id}",
                "version: 0.1.0",
                "type: fetch",
                "entrypoint: module.py",
                "catalog_tier: small",
                f"description: {description}",
                "managed_paths:",
                "  - module.yaml",
            ]
        ),
        encoding="utf-8",
    )


def test_find_sources_ranks_workspace_custom_modules(tmp_path: Path) -> None:
    workspace_root = tmp_path / "sancho-workspace"
    _write_custom_module(workspace_root)
    candidates = find_sources("protected bike lane washington", workspace_root=workspace_root)
    custom = next(c for c in candidates if c.module_id == "fetch.custom.dc_bike_lanes")
    assert custom.kind == "custom"
    assert custom.description


def test_find_sources_custom_override_replaces_builtin_entry(tmp_path: Path) -> None:
    workspace_root = tmp_path / "sancho-workspace"
    _write_custom_module(
        workspace_root,
        module_id="fetch.world_bank",
        dirname="world_bank",
        description="World Bank population and economy indicators (patched request handling)",
    )
    candidates = find_sources("world bank population indicator", workspace_root=workspace_root)
    world_bank = [c for c in candidates if c.module_id == "fetch.world_bank"]
    assert len(world_bank) == 1
    assert world_bank[0].kind == "custom"


def test_find_sources_sparse_override_keeps_module_discoverable(tmp_path: Path) -> None:
    """An override whose module.yaml has no description must not hide the
    module from queries the bundled text would have matched."""
    workspace_root = tmp_path / "sancho-workspace"
    module_dir = workspace_root / "custom" / "fetch" / "world_bank"
    module_dir.mkdir(parents=True)
    (module_dir / "module.yaml").write_text(
        "\n".join(
            [
                "id: fetch.world_bank",
                "version: 0.1.0",
                "type: fetch",
                "entrypoint: module.py",
                "catalog_tier: small",
                "managed_paths:",
                "  - module.yaml",
            ]
        ),
        encoding="utf-8",
    )
    baseline = find_sources("world bank population indicator")
    assert any(c.module_id == "fetch.world_bank" for c in baseline)
    candidates = find_sources("world bank population indicator", workspace_root=workspace_root)
    world_bank = [c for c in candidates if c.module_id == "fetch.world_bank"]
    assert len(world_bank) == 1
    assert world_bank[0].kind == "custom"
    assert world_bank[0].description  # inherited from the bundled manifest


def test_find_sources_tolerates_broken_custom_manifest(tmp_path: Path) -> None:
    workspace_root = tmp_path / "sancho-workspace"
    _write_custom_module(workspace_root)
    broken_dir = workspace_root / "custom" / "fetch" / "broken"
    broken_dir.mkdir(parents=True)
    (broken_dir / "module.yaml").write_text("id: [unclosed", encoding="utf-8")

    candidates = find_sources("protected bike lane washington", workspace_root=workspace_root)
    assert any(c.module_id == "fetch.custom.dc_bike_lanes" for c in candidates)


def test_find_sources_without_workspace_matches_bundled_only(tmp_path: Path) -> None:
    with_missing = find_sources("census ACS state", workspace_root=tmp_path / "nowhere")
    without = find_sources("census ACS state")
    assert [c.module_id for c in with_missing] == [c.module_id for c in without]


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
        assert "kind" in c and c["kind"] in {"pack", "module", "custom"}
        assert "score" in c
        assert "reasons" in c
