from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main

# A minimal JSON-stat 2.0 payload as the Eurostat statistics API returns it:
# values keyed by a linear index over the dimension sizes (geo x time).
JSONSTAT = {
    "version": "2.0",
    "class": "dataset",
    "label": "Unemployment rate -- annual data",
    "id": ["geo", "time"],
    "size": [2, 2],
    "dimension": {
        "geo": {"category": {"index": {"DE": 0, "FR": 1}, "label": {"DE": "Germany", "FR": "France"}}},
        "time": {"category": {"index": {"2023": 0, "2024": 1}, "label": {"2023": "2023", "2024": "2024"}}},
    },
    "value": {"0": 3.0, "1": 3.4, "2": 7.3, "3": 7.4},
}


def test_eurostat_run_decodes_jsonstat_to_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    assert main(["init", "--path", str(tmp_path), "--yes"]) == 0
    monkeypatch.setattr(
        "sancho.runtime.http.HttpClient.request_json",
        lambda self, method, url, params=None, headers=None, json_body=None: JSONSTAT,
    )
    assert main(["add", "fetch.eurostat", "--workspace", str(tmp_path)]) == 0
    input_file = tmp_path / "input.json"
    input_file.write_text(
        json.dumps({"dataset": "une_rt_a", "filters": {"geo": ["DE", "FR"]}}),
        encoding="utf-8",
    )
    capsys.readouterr()
    rc = main([
        "run", "fetch.eurostat", "--workspace", str(tmp_path),
        "--input", str(input_file), "--full-output",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    rows = payload["output"]["rows"]
    assert len(rows) == 4
    # Linear index 0 -> (DE, 2023); labels attached only when they add info.
    assert rows[0] == {"geo": "DE", "geo_label": "Germany", "time": "2023", "value": 3.0}
    assert rows[3] == {"geo": "FR", "geo_label": "France", "time": "2024", "value": 7.4}
    assert payload["output"]["dataset_ref"] == "une_rt_a"
    assert payload["primary_output_path"]


def test_eurostat_requires_dataset_code(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["init", "--path", str(tmp_path), "--yes"]) == 0
    assert main(["add", "fetch.eurostat", "--workspace", str(tmp_path)]) == 0
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"filters": {"geo": "DE"}}), encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "run", "fetch.eurostat", "--workspace", str(tmp_path), "--input", str(input_file),
    ])
    assert rc != 0  # missing dataset code fails with guidance, not a fetch
