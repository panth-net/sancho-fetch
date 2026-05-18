from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_fetch_sample_world_bank_supports_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace = _init_workspace(tmp_path)
    monkeypatch.setattr(
        "sancho.runtime.http.HttpClient.request_json",
        lambda self, method, url, params=None, headers=None, json_body=None: [
            {"page": 1, "pages": 1},
            [{"country": {"id": "KE"}, "value": 100}, {"country": {"id": "GH"}, "value": 200}],
        ],
    )
    capsys.readouterr()

    rc = main(["fetch", "sample", "world_bank", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "world_bank"
    assert payload["module_id"] == "fetch.world_bank"
    assert payload["status"] == "ok"
    assert payload["catalog_state"] == "ready"
    assert payload["run_id"]
    assert payload["counts"] == {"reused": 0, "fetched": 1, "skipped": 0, "failed": 0}
    assert payload["cache_records_written"]
    assert payload["latest_record"]["module_id"] == "fetch.world_bank"
    assert payload["next_suggested_command"].startswith("sancho fetch catalog world_bank")
    assert (workspace / "fetched-data").exists()
