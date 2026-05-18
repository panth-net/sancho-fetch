from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sancho.cli import main
from sancho import module_ops
from sancho.provider_discovery import run_module_discovery
from sancho.provider_kits import module_dir_for_template
from sancho.runtime.errors import ModuleExecutionError
from sancho.runtime.executor import run_module


def _copy_template_to_tmp(module_id: str, tmp_path: Path) -> Path:
    """Copy a template module dir to tmp so tests can regenerate its catalog
    without clobbering the committed seed in src/sancho/templates/modules/."""
    dst = tmp_path / module_id
    shutil.copytree(module_dir_for_template(module_id), dst)
    return dst


MIGRATED_AND_WAVE1_PROVIDERS = ["fetch.world_bank", "fetch.nyc_open_data", "fetch.fec", "fetch.cdc", "fetch.bls"]


def _template_dir(module_id: str) -> Path:
    return module_dir_for_template(module_id)


def test_world_bank_large_artifacts_are_generated(tmp_path: Path) -> None:
    module_dir = _copy_template_to_tmp("fetch.world_bank", tmp_path)
    result = run_module_discovery(module_dir, offline=False)
    assert result["provider"] == "fetch.world_bank"
    assert (module_dir / "catalog.json").exists()
    assert (module_dir / "catalog.meta.json").exists()

    payload = json.loads((module_dir / "catalog.json").read_text(encoding="utf-8"))
    assert payload["provider"] == "fetch.world_bank"
    assert isinstance(payload.get("families"), list)
    assert len(payload["families"]) > 0
    assert isinstance(payload.get("indices", {}).get("indicators"), list)


def test_nyc_open_data_large_artifacts_are_generated(tmp_path: Path) -> None:
    module_dir = _copy_template_to_tmp("fetch.nyc_open_data", tmp_path)
    result = run_module_discovery(module_dir, offline=False)
    assert result["provider"] == "fetch.nyc_open_data"
    assert (module_dir / "catalog.json").exists()
    assert (module_dir / "catalog.meta.json").exists()

    payload = json.loads((module_dir / "catalog.json").read_text(encoding="utf-8"))
    assert payload["provider"] == "fetch.nyc_open_data"
    assert isinstance(payload.get("families"), list)
    assert len(payload["families"]) > 0
    assert isinstance(payload.get("indices", {}).get("datasets"), list)


def test_wave1_provider_manifests_have_catalog_tier() -> None:
    for module_id in MIGRATED_AND_WAVE1_PROVIDERS:
        module_dir = _template_dir(module_id)
        manifest_text = (module_dir / "module.yaml").read_text(encoding="utf-8")
        assert "catalog_tier:" in manifest_text


def test_fetch_catalog_cli_lists_world_bank_families(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    assert main(["fetch", "catalog", "world_bank", "--workspace", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "v2.data.country_indicator" in out
    assert "companion.projects.search" in out


def test_fetch_catalog_cli_lists_nyc_open_data_families(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0
    assert main(["fetch", "catalog", "nyc_open_data", "--workspace", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "catalog.discovery.datasets" in out
    assert "soda.v3.query" in out


def test_module_catalog_refresh_world_bank_requires_live(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
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


def test_module_catalog_refresh_nyc_open_data_requires_live(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0
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


def test_module_catalog_refresh_is_strict_live_and_fails_on_discovery_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    def _raise_live_error(module_dir: Path, *, offline: bool = False) -> dict[str, str]:
        raise RuntimeError("forced live discovery failure")

    monkeypatch.setattr(module_ops, "run_module_discovery", _raise_live_error)

    result = main(
        [
            "module",
            "catalog",
            "refresh",
            "fetch.world_bank",
            "--workspace",
            str(tmp_path),
        ]
    )
    assert result == 1


def test_fetch_provider_invalid_family_match_has_clear_error(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.cdc", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    with pytest.raises(ModuleExecutionError, match="No catalog family matched"):
        run_module(
            workspace,
            module_id="fetch.cdc",
            input_payload={"base": "unknown", "method": "GET", "path": "/nope", "params": {}},
        )


def test_world_bank_param_validation_error(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    workspace = tmp_path / "sancho-workspace"

    with pytest.raises(ModuleExecutionError, match="Param 'per_page' must be type int"):
        run_module(
            workspace,
            module_id="fetch.world_bank",
            input_payload={
                "base": "v2",
                "method": "GET",
                "path": "/country/all/indicator/SP.POP.TOTL",
                "params": {"format": "json", "per_page": "1000"},
            },
        )


def test_fetch_run_cli_world_bank_direct_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        if "api.worldbank.org" in url:
            return [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 1}]]
        return {"ok": True}

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    params = json.dumps({"format": "json", "per_page": 1000})
    assert (
        main(
            [
                "fetch",
                "run",
                "world_bank",
                "--workspace",
                str(tmp_path),
                "--base",
                "v2",
                "--path",
                "/country/all/indicator/SP.POP.TOTL",
                "--params",
                params,
            ]
        )
        == 0
    )


def test_fetch_run_cli_nyc_open_data_direct_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        if "/resource/erm2-nwe9.json" in url:
            return [{"unique_key": "1", "complaint_type": "Noise"}]
        return {"ok": True}

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0

    params = json.dumps({"$limit": 5})
    assert (
        main(
            [
                "fetch",
                "run",
                "nyc_open_data",
                "--workspace",
                str(tmp_path),
                "--base",
                "nyc_v2",
                "--path",
                "/resource/erm2-nwe9.json",
                "--params",
                params,
            ]
        )
        == 0
    )


def test_nyc_v3_requires_app_token(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0
    workspace = tmp_path / "sancho-workspace"

    with pytest.raises(ModuleExecutionError, match="Missing required env vars 'SODA_API_KEY_ID' and 'SODA_API_KEY_SECRET'"):
        run_module(
            workspace,
            module_id="fetch.nyc_open_data",
            input_payload={
                "base": "nyc_v3",
                "method": "POST",
                "path": "/api/v3/views/erm2-nwe9/query.json",
                "body": {"query": "SELECT * LIMIT 1"},
            },
        )


def test_fetch_run_cli_fec_direct_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        if "/candidates/search/" in url:
            return {"results": [{"candidate_id": "P00000001"}]}
        return {"ok": True}

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.fec", "--workspace", str(tmp_path)]) == 0

    params = json.dumps({"q": "smith", "per_page": 10})
    assert (
        main(
            [
                "fetch",
                "run",
                "fec",
                "--workspace",
                str(tmp_path),
                "--base",
                "v1",
                "--path",
                "/candidates/search/",
                "--params",
                params,
            ]
        )
        == 0
    )
