from __future__ import annotations

import os
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.runtime.executor import run_module


pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.getenv("SANCHO_LIVE_GATE", "").strip() == "1"


def _require_live_gate() -> None:
    if not _live_enabled():
        pytest.skip("Live gate disabled. Set SANCHO_LIVE_GATE=1 to run real API integration checks.")


def test_live_gate_wave1_provider_kits(tmp_path: Path) -> None:
    _require_live_gate()

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0
    assert main(["add", "fetch.cdc", "--workspace", str(tmp_path)]) == 0
    assert main(["add", "fetch.bls", "--workspace", str(tmp_path)]) == 0
    assert main(["add", "fetch.fec", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"

    world_bank = run_module(
        workspace,
        module_id="fetch.world_bank",
        input_payload={
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
            "params": {"format": "json", "per_page": 1000},
        },
    )
    assert isinstance(world_bank.output.get("rows"), list)
    assert len(world_bank.output["rows"]) > 0

    nyc_open_data = run_module(
        workspace,
        module_id="fetch.nyc_open_data",
        input_payload={
            "base": "nyc_v2",
            "method": "GET",
            "path": "/resource/erm2-nwe9.json",
            "params": {"$limit": 10},
        },
    )
    assert isinstance(nyc_open_data.output.get("rows"), list)
    assert len(nyc_open_data.output["rows"]) > 0

    cdc = run_module(
        workspace,
        module_id="fetch.cdc",
        input_payload={
            "base": "resource",
            "method": "GET",
            "path": "/bi63-dtpu.json",
            "params": {"$limit": 10},
        },
    )
    assert isinstance(cdc.output.get("rows"), list)
    assert len(cdc.output["rows"]) > 0

    bls = run_module(
        workspace,
        module_id="fetch.bls",
        input_payload={
            "base": "v2_latest",
            "method": "POST",
            "path": "/timeseries/data/",
            "body": {"seriesid": ["CUUR0000SA0"], "latest": True},
        },
    )
    assert isinstance(bls.output.get("rows"), list)
    assert len(bls.output["rows"]) > 0

    data_gov_key = os.getenv("DATA_GOV_API_KEY", "").strip()
    if data_gov_key:
        fec = run_module(
            workspace,
            module_id="fetch.fec",
            input_payload={
                "base": "v1",
                "method": "GET",
                "path": "/candidates/search/",
                "params": {"q": "smith", "per_page": 10},
            },
        )
        assert isinstance(fec.output.get("rows"), list)
        assert len(fec.output["rows"]) > 0
