"""Live integration tests for file-download modules (ZIP, XLSX, HTML scrape).

Some modules require openpyxl for XLSX parsing — tests skip if not installed.
Run with: SANCHO_LIVE_GATE=1 pytest tests/test_live_download.py -v
Skip large downloads: SANCHO_LIVE_GATE=1 pytest tests/test_live_download.py -v -m "not slow"
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _live_helpers import (
    add_and_run,
    assert_has_rows,
    assert_output_shape,
    assert_raw_saved,
    assert_row_fields,
    init_workspace,
    require_live_gate,
)

pytestmark = pytest.mark.live


def _require_openpyxl():
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        pytest.skip("openpyxl not installed — pip install openpyxl")


@pytest.fixture(scope="module")
def live_ws(tmp_path_factory):
    require_live_gate()
    tmp = tmp_path_factory.mktemp("live_download")
    ws = init_workspace(tmp)
    return ws


# ── ZIP + CSV extraction ─────────────────────────────────────────────────


@pytest.mark.slow
def test_live_vdem(live_ws):
    out = add_and_run(live_ws, "fetch.vdem", {
        "version": "14",
        "indicators": ["v2x_polyarchy"],
        "country": "USA",
        "year_min": 2020,
        "year_max": 2022,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_row_fields(out, ["country_name", "year"])
    assert_raw_saved(live_ws, "fetch.vdem")


def test_live_nd_gain(live_ws):
    out = add_and_run(live_ws, "fetch.nd_gain", {
        "country": "USA",
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.nd_gain")


# ── XLSX download + parse (require openpyxl) ─────────────────────────────


def test_live_fsi(live_ws):
    _require_openpyxl()
    out = add_and_run(live_ws, "fetch.fsi")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    assert_raw_saved(live_ws, "fetch.fsi")


def test_live_sdg_index(live_ws):
    _require_openpyxl()
    out = add_and_run(live_ws, "fetch.sdg_index")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_ti_cpi(live_ws):
    _require_openpyxl()
    out = add_and_run(live_ws, "fetch.ti_cpi")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


def test_live_wjp_rule_of_law(live_ws):
    _require_openpyxl()
    out = add_and_run(live_ws, "fetch.wjp_rule_of_law")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)


# ── HTML scrape for file manifests ───────────────────────────────────────


def test_live_brfss(live_ws):
    out = add_and_run(live_ws, "fetch.brfss", {"year": 2022})
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")


def test_live_brfss_latest_year_all_files(live_ws):
    """All downloadable files for 2023 — broadest filter."""
    out = add_and_run(live_ws, "fetch.brfss", {"year": 2023})
    assert_has_rows(out)
    rows = out["rows"]
    # Should include multiple file kinds.
    kinds = {r.get("file_kind") for r in rows if isinstance(r, dict)}
    assert len(kinds) >= 2, f"expected multiple file_kinds, got {kinds}"


def test_live_brfss_codebook_2022(live_ws):
    """Codebook only for 2022."""
    out = add_and_run(live_ws, "fetch.brfss", {"year": 2022, "file_kind": "codebook"})
    assert_has_rows(out)
    rows = out["rows"]
    assert all(
        r.get("file_kind") == "codebook" for r in rows if isinstance(r, dict)
    ), f"expected codebook-only rows, got kinds {[r.get('file_kind') for r in rows[:3]]}"


def test_live_brfss_data_files_2021(live_ws):
    """SAS XPORT data files for 2021 — exercises the conditional file_kind filter."""
    out = add_and_run(live_ws, "fetch.brfss", {"year": 2021, "file_kind": "data_xpt"})
    assert_has_rows(out)
    rows = out["rows"]
    assert all(
        r.get("file_kind") == "data_xpt" for r in rows if isinstance(r, dict)
    ), f"expected data_xpt-only rows, got kinds {[r.get('file_kind') for r in rows[:3]]}"
    assert any(
        "XPT" in (r.get("url") or "").upper()
        for r in rows if isinstance(r, dict)
    ), f"expected URLs containing XPT, got {[r.get('url') for r in rows[:3]]}"


# ── CDC NHIS (P1 health source) ──────────────────────────────────────────


@pytest.mark.slow
def test_live_cdc_nhis_adult_2023_default(live_ws):
    """2023 adult NHIS file — default 1000 rows, ~600 columns."""
    out = add_and_run(live_ws, "fetch.cdc.nhis")
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    raw = out["raw"]
    assert raw["total_columns"] > 500, (
        f"NHIS adult file should have 500+ columns, got {raw['total_columns']}"
    )
    assert raw["total_rows_in_file"] > 25_000, (
        f"NHIS adult 2023 should have ~30K rows, got {raw['total_rows_in_file']}"
    )


def test_live_cdc_nhis_adult_2023_small_sample(live_ws):
    """2023 adult NHIS — limited to 100 rows for quick smoke test."""
    out = add_and_run(live_ws, "fetch.cdc.nhis", {
        "year": 2023, "file_kind": "adult", "limit": 100,
    })
    assert len(out["rows"]) == 100
    sample = out["rows"][0]
    # NHIS rows contain a primary sampling unit (PPSU) and stratum (PSTRAT).
    assert "PPSU" in sample, (
        f"expected PPSU in NHIS row, got keys {list(sample.keys())[:8]}"
    )


@pytest.mark.slow
def test_live_cdc_nhis_child_2023(live_ws):
    """2023 child NHIS file — child-specific variables."""
    out = add_and_run(live_ws, "fetch.cdc.nhis", {
        "year": 2023, "file_kind": "child", "limit": 100,
    })
    assert_has_rows(out)
    raw = out["raw"]
    # Child file is smaller than adult
    assert raw["total_rows_in_file"] > 5_000


@pytest.mark.slow
def test_live_cdc_nhis_adult_2022(live_ws):
    """2022 adult NHIS file."""
    out = add_and_run(live_ws, "fetch.cdc.nhis", {
        "year": 2022, "file_kind": "adult", "limit": 100,
    })
    assert_has_rows(out)


def test_live_cdc_nhis_paradata_2023(live_ws):
    """2023 paradata file (smaller)."""
    out = add_and_run(live_ws, "fetch.cdc.nhis", {
        "year": 2023, "file_kind": "paradata", "limit": 100,
    })
    assert_has_rows(out)


# ── CDC NHANES (P1 health source, requires pyreadstat) ──────────────────


def _require_pyreadstat():
    try:
        import pyreadstat  # noqa: F401
    except ImportError:
        pytest.skip("pyreadstat not installed — pip install pyreadstat")


def test_live_cdc_nhanes_demo_2017_2018(live_ws):
    """NHANES 2017-2018 Demographics file (cycle J)."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.cdc.nhanes", {
        "cycle": "J", "component": "DEMO", "limit": 100,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    sample = out["rows"][0]
    # NHANES respondents have a SEQN (sequence number) identifier.
    assert "SEQN" in sample, (
        f"expected SEQN in NHANES row, got keys {list(sample.keys())[:8]}"
    )
    # 2017-2018 cycle had ~9,254 respondents in DEMO_J
    assert out["raw"]["total_rows_in_file"] > 8000, (
        f"NHANES 2017-2018 DEMO should have ~9K respondents, "
        f"got {out['raw']['total_rows_in_file']}"
    )


def test_live_cdc_nhanes_bmx_2017_2018(live_ws):
    """NHANES 2017-2018 Body Measures (BMX_J)."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.cdc.nhanes", {
        "cycle": "J", "component": "BMX", "limit": 100,
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # BMX has BMXWT (weight) and BMXHT (height).
    assert "BMXWT" in sample, (
        f"expected BMXWT in BMX row, got keys {list(sample.keys())[:8]}"
    )


def test_live_cdc_nhanes_bpx_2017_2018(live_ws):
    """NHANES 2017-2018 Blood Pressure (BPX_J)."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.cdc.nhanes", {
        "cycle": "J", "component": "BPX", "limit": 100,
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # BPX has systolic readings BPXSY1, BPXSY2, BPXSY3.
    assert any(k.startswith("BPX") for k in sample.keys()), (
        f"expected BPX-prefixed columns, got keys {list(sample.keys())[:8]}"
    )


def test_live_cdc_nhanes_demo_2021_2023(live_ws):
    """NHANES 2021-2023 Demographics (cycle L)."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.cdc.nhanes", {
        "cycle": "L", "component": "DEMO", "limit": 100,
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    assert "SEQN" in sample


def test_live_cdc_nhanes_ghb_2017_2018(live_ws):
    """NHANES 2017-2018 HbA1c (GHB) — diabetes biomarker."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.cdc.nhanes", {
        "cycle": "J", "component": "GHB", "limit": 100,
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    # LBXGH is the glycohemoglobin lab value.
    assert "LBXGH" in sample, (
        f"expected LBXGH in GHB row, got keys {list(sample.keys())[:8]}"
    )


# ── AHRQ MEPS (P1 health source, requires pyreadstat) ───────────────────


@pytest.mark.slow
def test_live_ahrq_meps_full_year_2021(live_ws):
    """MEPS 2021 Full Year Consolidated (h233) — 28K respondents, 1488 cols."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.ahrq.meps", {
        "puf_id": "h233", "limit": 100,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    raw = out["raw"]
    assert raw["total_rows_in_file"] > 25_000, (
        f"MEPS 2021 should have ~28K respondents, got {raw['total_rows_in_file']}"
    )
    assert raw["total_columns"] > 1000, (
        f"MEPS Full Year file should have 1000+ cols, got {raw['total_columns']}"
    )
    sample = out["rows"][0]
    # MEPS uses DUPERSID as the cross-year person identifier.
    assert "DUPERSID" in sample, (
        f"expected DUPERSID in MEPS row, got keys {list(sample.keys())[:8]}"
    )


@pytest.mark.slow
def test_live_ahrq_meps_full_year_2022(live_ws):
    """MEPS 2022 Full Year Consolidated (h243)."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.ahrq.meps", {
        "puf_id": "h243", "limit": 100,
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    assert "DUPERSID" in sample


@pytest.mark.slow
def test_live_ahrq_meps_full_year_2019(live_ws):
    """MEPS 2019 Full Year Consolidated (h216)."""
    _require_pyreadstat()
    out = add_and_run(live_ws, "fetch.ahrq.meps", {
        "puf_id": "h216", "limit": 100,
    })
    assert_has_rows(out)


# ── ATSDR Social Vulnerability Index (P1 health source, ~60MB CSV) ───────


@pytest.mark.slow
def test_live_atsdr_svi_california_2022(live_ws):
    """SVI 2022 census tracts for California."""
    out = add_and_run(live_ws, "fetch.atsdr.svi", {
        "year": 2022, "state": "CA", "limit": 100,
    })
    assert_output_shape(out, "dataset_ref", "rows", "retrieved_at")
    assert_has_rows(out)
    sample = out["rows"][0]
    state_col = next(
        (k for k in sample if k.upper() in ("STATE", "ST_ABBR")), None,
    )
    assert state_col, f"expected STATE column, got keys {list(sample.keys())[:10]}"
    assert str(sample[state_col]).upper() == "CALIFORNIA" or sample[state_col] == "CA"
    # SVI rows have an RPL_THEMES overall percentile
    assert any(k.startswith("RPL_THEMES") for k in sample.keys()), (
        f"expected RPL_THEMES in SVI row, got {list(sample.keys())[:15]}"
    )


@pytest.mark.slow
def test_live_atsdr_svi_texas_2022(live_ws):
    """SVI 2022 census tracts for Texas."""
    out = add_and_run(live_ws, "fetch.atsdr.svi", {
        "year": 2022, "state": "TX", "limit": 100,
    })
    assert_has_rows(out)
    sample = out["rows"][0]
    state_col = next(
        (k for k in sample if k.upper() in ("STATE", "ST_ABBR")), None,
    )
    assert state_col
    assert str(sample[state_col]).upper() in ("TEXAS", "TX")


@pytest.mark.slow
def test_live_atsdr_svi_california_2020(live_ws):
    """SVI 2020 — compare year-over-year vs 2022."""
    out = add_and_run(live_ws, "fetch.atsdr.svi", {
        "year": 2020, "state": "CA", "limit": 100,
    })
    assert_has_rows(out)


@pytest.mark.slow
def test_live_atsdr_svi_virginia_2022(live_ws):
    """SVI 2022 census tracts for Virginia."""
    out = add_and_run(live_ws, "fetch.atsdr.svi", {
        "year": 2022, "state": "VA", "limit": 100,
    })
    assert_has_rows(out)
