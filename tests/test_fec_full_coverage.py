from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import requests
import yaml

from sancho.cli import main
from sancho.runtime.errors import ModuleExecutionError
from sancho.runtime.executor import run_module


ROOT = Path(__file__).resolve().parents[1]
FEC_DIR = ROOT / "src" / "sancho" / "templates" / "modules" / "fetch.fec"


def _load_blueprint() -> Any:
    path = FEC_DIR / "catalog_blueprint.py"
    spec = importlib.util.spec_from_file_location("fec_catalog_blueprint_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _init_fec_workspace(tmp_path: Path) -> Path:
    assert main(["init", "--path", str(tmp_path), "--yes"]) == 0
    assert main(["add", "fetch.fec", "--workspace", str(tmp_path)]) == 0
    return tmp_path / "sancho-workspace"


def test_fec_swagger_fixture_generates_one_family_per_json_get_path() -> None:
    blueprint = _load_blueprint()
    swagger = {
        "produces": ["application/json"],
        "paths": {
            "/v1/committees/": {
                "get": {
                    "tags": ["committee"],
                    "description": "Fetch committees.",
                    "parameters": [
                        {"name": "api_key", "in": "query", "type": "string"},
                        {"name": "committee_type", "in": "query", "type": "array", "collectionFormat": "multi"},
                        {"name": "per_page", "in": "query", "type": "integer", "default": 20},
                    ],
                }
            },
            "/v1/schedules/schedule_a/": {
                "get": {"tags": ["receipts"], "description": "Itemized receipts.", "parameters": []}
            },
            "/v1/schedules/schedule_e/": {
                "get": {"tags": ["independent expenditures"], "description": "Independent expenditures.", "parameters": []}
            },
            "/v1/download.csv": {
                "get": {"produces": ["text/csv"], "description": "Not JSON.", "parameters": []}
            },
        },
    }

    families = blueprint.build_families(swagger)

    assert len(families) == 3
    paths = {family["path_templates"][0] for family in families}
    assert paths == {"/committees/", "/schedules/schedule_a/", "/schedules/schedule_e/"}
    committees = next(family for family in families if family["path_templates"] == ["/committees/"])
    assert committees["id"] == "v1.committees.search"
    assert committees["allow_unknown_query_params"] is True
    assert "api_key" not in committees["query_params"]
    assert committees["query_params"]["committee_type"]["type"] == "list"


def test_fec_catalog_has_full_openfec_surface_and_super_pac_workflows() -> None:
    catalog = json.loads((FEC_DIR / "catalog.json").read_text(encoding="utf-8"))
    meta = json.loads((FEC_DIR / "catalog.meta.json").read_text(encoding="utf-8"))
    paths = {family["path_templates"][0] for family in catalog["families"]}

    assert meta["stats"]["family_count"] >= 80
    assert "/schedules/schedule_a/" in paths
    assert "/schedules/schedule_e/" in paths
    assert "/filings/" in paths
    assert "/committee/{committee_id}/reports/" in paths
    assert catalog["indices"]["super_pac_workflows"]
    assert catalog["notices"]["contributor_usage"]["source"].startswith("https://www.fec.gov/")


def test_fec_manifest_declares_key_and_signup_help() -> None:
    manifest = yaml.safe_load((FEC_DIR / "module.yaml").read_text(encoding="utf-8"))
    assert manifest["api_key_env"] == "DATA_GOV_API_KEY"
    assert manifest["api_key_docs"]["DATA_GOV_API_KEY"] == "https://api.data.gov/signup/"


def test_fec_missing_key_is_reported_as_setup_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    workspace = _init_fec_workspace(tmp_path)

    with pytest.raises(ModuleExecutionError, match="DATA_GOV_API_KEY"):
        run_module(
            workspace,
            "fetch.fec",
            {
                "path": "/candidates/totals/",
                "params": {"cycle": 2024, "office": "H", "state": "NH", "per_page": 5},
            },
        )

    runs_log = workspace / "logs" / "runs.jsonl"
    finished_events = [
        json.loads(line)
        for line in runs_log.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("event_type") == "run_finished"
    ]
    finished = finished_events[-1]
    assert finished["status"] == "skipped_needs_key"
    assert "https://api.data.gov/signup/" in finished["error_message"]
    packet = Path(finished["repair_packet_path"]).read_text(encoding="utf-8")
    assert "https://api.data.gov/signup/" in packet
    assert "sancho-workspace/.env" in packet


def test_fec_provider_errors_redact_query_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = "super-secret-data-gov-key"

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        response = requests.Response()
        response.status_code = 422
        response.url = f"https://api.open.fec.gov/v1/example/?api_key={secret}&state=NH"
        response._content = f'{{"error": "bad api_key={secret}"}}'.encode("utf-8")
        raise requests.HTTPError(f"422 Client Error for url: {response.url}", response=response)

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", secret)
    workspace = _init_fec_workspace(tmp_path)

    with pytest.raises(ModuleExecutionError) as excinfo:
        run_module(
            workspace,
            "fetch.fec",
            {
                "path": "/committees/",
                "params": {"committee_type": "O", "per_page": 1, "api_key": secret, "token": secret},
            },
        )

    assert secret not in str(excinfo.value)
    assert "api_key=[REDACTED]" in str(excinfo.value)
    run_events = [
        json.loads(line)
        for line in (workspace / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert secret not in json.dumps(run_events)
    assert any("[REDACTED]" in json.dumps(event.get("request_summary", {})) for event in run_events)
    finished_events = [event for event in run_events if event.get("event_type") == "run_finished"]
    finished = finished_events[-1]
    assert secret not in finished["error_message"]
    packet = Path(finished["repair_packet_path"]).read_text(encoding="utf-8")
    assert secret not in packet
    assert "api_key=[REDACTED]" in packet


def test_fec_maximizes_per_page_unless_caller_sets_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        request_params = dict(params or {})
        calls.append(request_params)
        per_page = int(request_params.get("per_page", 20))
        return {
            "pagination": {"count": 200, "is_count_exact": True, "page": 1, "pages": max(1, 200 // per_page), "per_page": per_page},
            "results": [{"committee_id": "C1"}],
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    auto = run_module(
        workspace,
        "fetch.fec",
        {"path": "/committees/", "params": {"committee_type": "O"}},
    ).output
    assert auto["params"]["per_page"] == 100
    assert calls[-1]["per_page"] == 100

    explicit = run_module(
        workspace,
        "fetch.fec",
        {"path": "/committees/", "params": {"committee_type": "O", "per_page": 7}},
    ).output
    assert explicit["params"]["per_page"] == 7
    assert calls[-1]["per_page"] == 7

    page_size = run_module(
        workspace,
        "fetch.fec",
        {
            "path": "/committees/",
            "params": {"committee_type": "P"},
            "pagination": {"page_size": 50},
        },
    ).output
    assert page_size["params"]["per_page"] == 50
    assert calls[-1]["per_page"] == 50


def test_fec_runtime_accepts_super_pac_core_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        return {
            "pagination": {"count": 1, "is_count_exact": True, "page": 1, "pages": 1, "per_page": 1},
            "results": [{"url": url, "params": params or {}}],
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    payloads = [
        {"path": "/committees/", "params": {"committee_type": "O", "per_page": 1}},
        {"path": "/schedules/schedule_a/", "params": {"committee_id": "C00000001", "two_year_transaction_period": 2024, "per_page": 1}},
        {"path": "/schedules/schedule_e/", "params": {"committee_id": "C00000001", "cycle": 2024, "per_page": 1}},
        {"path": "/filings/", "params": {"committee_id": "C00000001", "per_page": 1}},
        {"path": "/committee/C00000001/reports/", "params": {"cycle": 2024, "per_page": 1}},
    ]

    outputs = [run_module(workspace, "fetch.fec", payload).output for payload in payloads]

    assert all(output["rows"] for output in outputs)
    assert outputs[0]["family_id"] == "v1.committees.search"
    assert outputs[0]["params"] == {"committee_type": "O", "per_page": 1}
    assert outputs[1]["usage_notice"]["source"].startswith("https://www.fec.gov/")
    assert all(output["pagination"]["fetched_rows"] == 1 for output in outputs)


def test_fec_single_page_returns_more_available_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        return {
            "pagination": {"count": 5, "is_count_exact": True, "page": 1, "pages": 3, "per_page": 2},
            "results": [{"committee_id": "C1"}, {"committee_id": "C2"}],
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    out = run_module(
        workspace,
        "fetch.fec",
        {"path": "/committees/", "params": {"committee_type": "O", "per_page": 2}},
    ).output

    assert len(out["rows"]) == 2
    assert out["pagination"]["has_more"] is True
    assert out["pagination"]["next_params"]["page"] == 2
    assert out["pagination"]["estimated_remaining_api_calls"] == 2


def test_fec_bounded_page_pagination_fetches_multiple_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        request_params = dict(params or {})
        calls.append(request_params)
        page = int(request_params.get("page", 1))
        return {
            "pagination": {"count": 6, "is_count_exact": True, "page": page, "pages": 3, "per_page": 2},
            "results": [{"page": page, "row": 1}, {"page": page, "row": 2}],
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    out = run_module(
        workspace,
        "fetch.fec",
        {
            "path": "/committees/",
            "params": {"committee_type": "O", "per_page": 2},
            "pagination": {"mode": "pages", "max_pages": 2},
        },
    ).output

    assert [call.get("page", 1) for call in calls] == [1, 2]
    assert all("q" not in call for call in calls)
    assert len(out["rows"]) == 4
    assert out["pagination"]["stop_reason"] == "max_pages"
    assert out["pagination"]["next_params"]["page"] == 3


def test_fec_cursor_pagination_uses_last_indexes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        request_params = dict(params or {})
        calls.append(request_params)
        if len(calls) == 1:
            return {
                "pagination": {
                    "count": 4,
                    "is_count_exact": False,
                    "pages": 2,
                    "per_page": 2,
                    "last_indexes": {
                        "last_index": "abc",
                        "last_contribution_receipt_date": "2024-01-01",
                    },
                },
                "results": [{"sub_id": "1"}, {"sub_id": "2"}],
            }
        return {
            "pagination": {"count": 4, "is_count_exact": False, "pages": 2, "per_page": 2},
            "results": [{"sub_id": "3"}, {"sub_id": "4"}],
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    out = run_module(
        workspace,
        "fetch.fec",
        {
            "path": "/schedules/schedule_a/",
            "params": {"committee_id": "C00000001", "per_page": 2},
            "pagination": {"mode": "pages", "max_pages": 2},
        },
    ).output

    assert calls[1]["last_index"] == "abc"
    assert calls[1]["last_contribution_receipt_date"] == "2024-01-01"
    assert len(out["rows"]) == 4
    assert out["pagination"]["has_more"] is False


def test_fec_all_pagination_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    with pytest.raises(ModuleExecutionError, match="pagination.mode='all' requires"):
        run_module(
            workspace,
            "fetch.fec",
            {"path": "/committees/", "pagination": {"mode": "all"}},
        )


def test_fec_large_single_page_estimate_adds_notice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_request_json(self, method, url, params=None, headers=None, json_body=None):
        return {
            "pagination": {"count": 1_000_000, "is_count_exact": False, "page": 1, "pages": 50000, "per_page": 20},
            "results": [{"committee_id": "C1"}],
        }

    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", fake_request_json)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")
    workspace = _init_fec_workspace(tmp_path)

    out = run_module(workspace, "fetch.fec", {"path": "/committees/"}).output

    assert out["pagination"]["has_more"] is True
    assert out["pagination"]["estimated_total_pages"] == 50000
    assert "large result set" in out["pagination"]["large_result_notice"]
