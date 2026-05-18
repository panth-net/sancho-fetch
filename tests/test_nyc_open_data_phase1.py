from __future__ import annotations

from pathlib import Path

import pytest
import requests

from sancho.cli import main
from sancho.runtime.errors import ModuleExecutionError
from sancho.runtime.executor import run_module


def test_nyc_open_data_add_uses_seeded_fallback_when_live_discovery_source_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real_get = requests.get

    def failing_get(url, params=None, timeout=30, headers=None, **kwargs):
        if "api.us.socrata.com/api/catalog/v1" in url:
            raise requests.RequestException("forced failure")
        return real_get(url, params=params, timeout=timeout, headers=headers, **kwargs)

    monkeypatch.setattr("requests.get", failing_get)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path), "--discover"]) == 0
    err = capsys.readouterr().err
    assert "WARNING: Provider discovery fallback for 'fetch.nyc_open_data'" in err
    assert "forced failure" in err


def test_nyc_open_data_runtime_rejects_unknown_catalog_path(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.nyc_open_data", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    with pytest.raises(ModuleExecutionError, match="No catalog family matched"):
        run_module(
            workspace,
            module_id="fetch.nyc_open_data",
            input_payload={"base": "nyc_v2", "method": "GET", "path": "/unknown/path", "params": {"$limit": 1}},
        )
