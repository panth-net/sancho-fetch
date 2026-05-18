from __future__ import annotations

import json
from pathlib import Path

import yaml

from sancho.cli import main
from sancho.cli_find import find_sources
from sancho.runtime.executor import run_module


ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "src" / "sancho" / "templates" / "modules" / "fetch.dc_open_data"


def test_dc_open_data_manifest_and_schema_shape() -> None:
    manifest = yaml.safe_load((MODULE_DIR / "module.yaml").read_text(encoding="utf-8"))

    assert manifest["id"] == "fetch.dc_open_data"
    assert manifest["catalog_tier"] == "small"
    assert manifest["entrypoint"] == "main.py:run"
    assert "schema.sample.json" in manifest["managed_paths"]
    assert "opendata.dc.gov" in manifest["sources"][0]["url"]


def test_dc_open_data_runtime_flattens_arcgis_features(
    monkeypatch,
    tmp_path: Path,
) -> None:
    page_calls: list[dict[str, object]] = []

    def feature(idx: int) -> dict[str, object]:
        descriptions = {
            1: "Pothole",
            2: "Pothole",
            3: "Bulk Collection",
            4: "Trash Collection",
            5: "Streetlight Repair",
        }
        return {
            "attributes": {
                "SERVICEREQUESTID": f"26-0000000{idx}",
                "SERVICECODEDESCRIPTION": descriptions[idx],
                "SERVICETYPECODEDESCRIPTION": "Transportation",
                "SERVICEORDERDATE": 1779067600000 + idx,
                "WARD": f"Ward {idx}",
                "STATUS_CODE": "OPEN",
            }
        }

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        assert method == "GET"
        params = dict(params or {})
        if not url.endswith("/query"):
            return {
                "maxRecordCount": 2,
                "advancedQueryCapabilities": {"supportsPagination": True},
            }
        if params.get("returnCountOnly") == "true":
            return {"count": 5}

        page_calls.append(params)
        assert params["returnGeometry"] == "false"
        assert params["resultRecordCount"] == 2
        offset = int(params["resultOffset"])
        rows = [feature(idx) for idx in range(1, 6)][offset: offset + 2]
        return {
            "features": rows,
            "exceededTransferLimit": offset + len(rows) < 5,
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)

    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.dc_open_data", "--workspace", str(tmp_path)]) == 0

    result = run_module(tmp_path / "sancho-workspace", "fetch.dc_open_data", {})

    assert result.status == "ok"
    output = result.output
    assert output["dataset_ref"] == "dc_open_data_service_requests"
    assert len(output["rows"]) == 5
    assert output["rows"][0]["SERVICEREQUESTID"] == "26-00000001"
    assert output["rows"][0]["SERVICECODEDESCRIPTION"] == "Pothole"
    assert output["pagination"]["page_size"] == 2
    assert output["pagination"]["max_record_count"] == 2
    assert output["pagination"]["total_count"] == 5
    assert output["pagination"]["fetched_pages"] == 3
    assert output["pagination"]["fetched_rows"] == 5
    assert output["pagination"]["has_more"] is False
    assert output["pagination"]["stop_reason"] == "complete"
    assert [call["resultOffset"] for call in page_calls] == [0, 2, 4]
    assert output["shape"]["row_count"] == 5
    assert output["shape"]["columns"] == [
        "SERVICECODEDESCRIPTION",
        "SERVICEORDERDATE",
        "SERVICEREQUESTID",
        "SERVICETYPECODEDESCRIPTION",
        "STATUS_CODE",
        "WARD",
    ]
    head_preview = "\n".join(
        json.dumps(row, sort_keys=True)
        for row in output["rows"][:5]
    )
    assert "SERVICEREQUESTID" in head_preview
    assert "Pothole" in head_preview
    assert "Bulk Collection" in head_preview
    assert "Streetlight Repair" in head_preview
    assert "Ward 5" in head_preview


def test_dc_open_data_human_prompts_are_discoverable() -> None:
    prompts = [
        "Show me recent 311 service requests in Washington DC.",
        "Pull DC open data about city service complaints by ward.",
        "I need Washington DC public service request records from the open data portal.",
    ]

    for prompt in prompts:
        ids = [candidate.module_id for candidate in find_sources(prompt, limit=8)]
        assert "fetch.dc_open_data" in ids, f"{prompt!r} returned {ids}"


def test_module_creation_guide_covers_ai_creation_workflow() -> None:
    guide = (ROOT / "project-docs" / "MODULE_CREATION_GUIDE.md").read_text(encoding="utf-8")
    required_phrases = [
        "README_ALL_INSTRUCTIONS.md",
        "Research the provider from official sources",
        "page-size limits",
        "assume the user wants all matching records",
        "Pick the closest existing module",
        "Never edit a user's real `.env`",
        "Write three broad human prompts",
        "Pagination test",
        "first five fetched rows",
        "`shape` and `pagination`",
        "Worked Example: Washington DC Open Data",
    ]

    for phrase in required_phrases:
        assert phrase in guide
