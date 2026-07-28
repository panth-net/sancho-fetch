from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.runtime.soft_validation import (
    missing_required_keys,
    required_env_keys,
    soft_validate_schema,
)


def test_soft_validate_returns_warnings_not_exceptions() -> None:
    schema = {"type": "object", "required": ["year"], "properties": {"year": {"type": "integer"}}}
    warnings = soft_validate_schema({"unrelated": "x"}, schema, label="input")
    assert any("missing declared field(s): year" in w for w in warnings)
    assert any("undeclared field(s): unrelated" in w for w in warnings)


def test_soft_validate_empty_schema_is_silent() -> None:
    assert soft_validate_schema({"any": "thing"}, None) == []
    assert soft_validate_schema({"any": "thing"}, {}) == []


def test_required_env_keys_handles_str_and_list_and_missing() -> None:
    assert required_env_keys({"api_key_env": "FOO"}) == ["FOO"]
    assert required_env_keys({"api_key_env": ["FOO", "BAR"]}) == ["FOO", "BAR"]
    assert required_env_keys({}) == []
    assert required_env_keys({"api_key_env": ""}) == []


def test_missing_required_keys_excludes_present_values() -> None:
    manifest = {"api_key_env": ["FOO", "BAR"]}
    assert missing_required_keys(manifest, {"FOO": "x"}) == ["BAR"]
    assert missing_required_keys(manifest, {"FOO": "x", "BAR": "y"}) == []
    assert missing_required_keys(manifest, {"FOO": "x", "BAR": ""}) == ["BAR"]


def test_executor_runs_with_soft_warnings_when_input_schema_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module with required input field should still run when missing — soft warning only."""
    workspace = tmp_path / WORKSPACE_DIRNAME
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    monkeypatch.setattr(
        "sancho.runtime.http.HttpClient.request_json",
        lambda self, method, url, params=None, headers=None, json_body=None:
            [{"page": 1, "pages": 1}, [{"v": 1}]],
    )
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Patch the installed module.yaml to *require* a property not in our input.
    module_yaml = workspace / "source" / "fetch" / "fetch_world_bank" / "module.yaml"
    manifest = yaml.safe_load(module_yaml.read_text(encoding="utf-8"))
    manifest["input_schema"] = {
        "type": "object",
        "required": ["mandatory_field"],
        "properties": {"mandatory_field": {"type": "string"}},
    }
    module_yaml.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({
        "base": "v2", "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
        "params": {"format": "json"},
    }), encoding="utf-8")
    # Soft validation: the run completes even though required field is missing.
    rc = main([
        "run", "fetch.world_bank",
        "--workspace", str(tmp_path),
        "--input", str(input_file),
    ])
    assert rc == 0


def test_executor_skips_when_required_api_key_declared_and_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / WORKSPACE_DIRNAME
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    module_yaml = workspace / "source" / "fetch" / "fetch_world_bank" / "module.yaml"
    manifest = yaml.safe_load(module_yaml.read_text(encoding="utf-8"))
    manifest["api_key_env"] = "SOME_REQUIRED_API_KEY"
    module_yaml.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    # Make sure the env var is NOT set.
    monkeypatch.delenv("SOME_REQUIRED_API_KEY", raising=False)
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({
        "base": "v2", "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
    }), encoding="utf-8")
    rc = main([
        "run", "fetch.world_bank",
        "--workspace", str(tmp_path),
        "--input", str(input_file),
    ])
    assert rc != 0
    errors_log = workspace / "logs" / "errors.jsonl"
    assert errors_log.exists()
    last = json.loads(errors_log.read_text(encoding="utf-8").splitlines()[-1])
    assert last["status"] == "skipped_needs_key"
    assert "SOME_REQUIRED_API_KEY" in last["error_message"]
