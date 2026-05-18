from __future__ import annotations

from pathlib import Path

import pytest
import requests

from sancho.cli import main
from sancho.runtime.errors import ModuleExecutionError
from sancho.runtime.executor import run_module


def test_world_bank_add_uses_seeded_fallback_when_live_discovery_source_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real_get = requests.get

    def failing_get(url, params=None, timeout=30, headers=None, **kwargs):
        if "api.worldbank.org/v2/indicator" in url:
            raise requests.RequestException("forced failure")
        return real_get(url, params=params, timeout=timeout, headers=headers, **kwargs)

    monkeypatch.setattr("requests.get", failing_get)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path), "--discover"]) == 0
    err = capsys.readouterr().err
    assert "WARNING: Provider discovery fallback for 'fetch.world_bank'" in err
    assert "forced failure" in err


def test_world_bank_runtime_rejects_unknown_catalog_path(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    with pytest.raises(ModuleExecutionError, match="No catalog family matched"):
        run_module(
            workspace,
            module_id="fetch.world_bank",
            input_payload={"base": "v2", "method": "GET", "path": "/unknown/path", "params": {"format": "json"}},
        )


def test_world_bank_runtime_accepts_direct_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        return [{"page": 1, "pages": 1}, [{"country": {"id": "US"}, "value": 1}]]

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    workspace = tmp_path / "sancho-workspace"

    result = run_module(
        workspace,
        module_id="fetch.world_bank",
        input_payload={
            "base": "v2",
            "method": "GET",
            "path": "/country/all/indicator/SP.POP.TOTL",
            "params": {"format": "json", "per_page": 1000},
        },
    )
    assert result.status == "ok"
    assert result.output["family_id"] == "v2.data.country_indicator"
