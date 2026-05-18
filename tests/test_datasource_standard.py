from __future__ import annotations

from pathlib import Path

import pytest

from sancho.cli import main


INTERNATIONAL_MODULES = [
    "fetch.vdem",
    "fetch.wgi",
    "fetch.undp_hdr",
    "fetch.ti_cpi",
    "fetch.fsi",
    "fetch.gpi",
    "fetch.rsf_press_freedom",
    "fetch.un_egdi",
    "fetch.wjp_rule_of_law",
    "fetch.sdg_index",
    "fetch.imf_cdis",
    "fetch.oecd_dac_crs",
    "fetch.nd_gain",
    "fetch.oecd_sdmx",
    "fetch.iati",
    "fetch.owid_catalog",
    "fetch.owid_charts",
    "fetch.atus",
    "fetch.brfss",
    "fetch.overture_maps",
    "fetch.wvs",
    "fetch.pew",
]


@pytest.mark.parametrize("module_id", INTERNATIONAL_MODULES)
def test_international_module_add_and_audit(tmp_path: Path, module_id: str) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", module_id, "--workspace", str(tmp_path)]) == 0
    assert main(["module", "audit", "--workspace", str(tmp_path)]) == 0


def test_module_audit_fails_when_world_bank_large_artifact_missing(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    module_dir = tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_world_bank"
    (module_dir / "catalog.meta.json").unlink()

    assert main(["module", "audit", "--workspace", str(tmp_path)]) == 1


def test_module_catalog_refresh_restores_world_bank_large_artifacts(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    module_dir = tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_world_bank"
    catalog_path = module_dir / "catalog.json"
    catalog_path.unlink()

    assert (
        main(
            [
                "module",
                "catalog",
                "refresh",
                "fetch.world_bank",
                "--workspace",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert catalog_path.exists()


def test_module_audit_fails_when_nyc_open_data_large_artifact_missing(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0

    module_dir = tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_nyc_open_data"
    (module_dir / "catalog.meta.json").unlink()

    assert main(["module", "audit", "--workspace", str(tmp_path)]) == 1


def test_module_catalog_refresh_restores_nyc_open_data_large_artifacts(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0

    module_dir = tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_nyc_open_data"
    catalog_path = module_dir / "catalog.json"
    catalog_path.unlink()

    assert (
        main(
            [
                "module",
                "catalog",
                "refresh",
                "fetch.nyc_open_data",
                "--workspace",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert catalog_path.exists()


def test_module_catalog_refresh_restores_cdc_large_meta_artifact(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.cdc", "--workspace", str(tmp_path)]) == 0

    module_dir = tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_cdc"
    meta_path = module_dir / "catalog.meta.json"
    meta_path.unlink()
    assert main(["module", "audit", "--workspace", str(tmp_path)]) == 1

    meta_path.write_text(
        """{
  "provider": "fetch.cdc",
  "schema_version": "1.0",
  "generated_at": "2026-03-29T00:00:00+00:00",
  "stats": {"family_count": 14},
  "discovery": {
    "mode": "manual_test",
    "sources": [
      {
        "url": "https://data.cdc.gov/api/views",
        "status": "ok",
        "fetched_at": "2026-03-29T00:00:00+00:00"
      }
    ]
  }
}
""",
        encoding="utf-8",
    )
    assert main(["module", "audit", "--workspace", str(tmp_path)]) == 0
