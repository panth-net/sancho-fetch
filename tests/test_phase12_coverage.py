"""Phase 12 — explicit coverage for every gameplan acceptance criterion.

Earlier phases already cover most of these; this file fills the named gaps
so each Phase 12 ticket's acceptance criteria has a direct test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main
from sancho.cli_cache import _status_for_module, _status_for_request
from sancho.constants import REQUIRED_DIRECTORIES, WORKSPACE_DIRNAME
from sancho.project_export import export_record_to_project
from sancho.templates.runtime.data_store import save_raw
from sancho.update_engine import (
    apply_updates_safe,
    check_updates,
    preview_updates_rich,
    rollback_update,
)


# ---------------------------------------------------------------------------
# Ticket 12.1 — Workspace contract
# ---------------------------------------------------------------------------


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_sancho_init_repairs_missing_fetched_data_logs_outputs(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    # Delete generated dirs as if the user emptied them.
    for sub in ("fetched-data", "logs", "outputs"):
        target = workspace / sub
        if target.exists():
            for child in target.iterdir():
                child.unlink()
            target.rmdir()
    # Re-running init must recreate them.
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    for sub in ("fetched-data", "logs", "outputs"):
        assert (workspace / sub).exists(), f"init failed to recreate {sub}"


def test_sancho_init_preserves_personal_files(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    # Drop personal files that should never be overwritten by init.
    instructions = workspace / "AI_INSTRUCTIONS.md"
    catalog = workspace / "DATASET_CATALOG.md"
    custom_module = workspace / "custom" / "fetch" / "my_module" / "module.yaml"
    custom_module.parent.mkdir(parents=True, exist_ok=True)
    custom_module.write_text("custom-module-yaml-marker", encoding="utf-8")
    playbook = workspace / "playbooks" / "my_playbook.yaml"
    playbook.write_text("playbook-marker", encoding="utf-8")
    env_text = "FRED_API_KEY=user-secret-do-not-touch\n"
    (workspace / ".env").write_text(env_text, encoding="utf-8")
    instructions_text = "USER WROTE THIS"
    catalog_text = "USER WROTE THIS TOO"
    instructions.write_text(instructions_text, encoding="utf-8")
    catalog.write_text(catalog_text, encoding="utf-8")

    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0

    assert custom_module.read_text(encoding="utf-8") == "custom-module-yaml-marker"
    assert playbook.read_text(encoding="utf-8") == "playbook-marker"
    assert (workspace / ".env").read_text(encoding="utf-8") == env_text
    assert instructions.read_text(encoding="utf-8") == instructions_text
    assert catalog.read_text(encoding="utf-8") == catalog_text


def test_new_workspace_never_creates_data_raw(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    for legacy in ("data", "data/raw", "data/refined", "data/outputs"):
        assert not (workspace / legacy).exists(), f"legacy path leaked: {legacy}"
    # Phase 1 tree should be in place instead.
    for new in ("fetched-data", "analysis-data", "outputs", "logs", "update-backups"):
        assert (workspace / new).exists()


# ---------------------------------------------------------------------------
# Ticket 12.2 — Cache / index
# ---------------------------------------------------------------------------


def _seed_record(workspace: Path, params: dict, raw=None) -> None:
    save_raw(
        data_raw_path=workspace / "fetched-data",
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.data.country_indicator",
        raw=raw if raw is not None else [{"v": 1}],
        params=params,
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
        fetched_at="2026-04-01T12:00:00+00:00",
    )


def test_cache_status_reports_partial_coverage_across_units(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    # Seed two distinct requests (different request keys, same family).
    _seed_record(workspace, {"format": "json", "country": "US"})
    _seed_record(workspace, {"format": "json", "country": "CA"})
    # Module-wide status: 2 records, both cached.
    summary = _status_for_module(workspace, "fetch.world_bank", max_age_seconds=None)
    assert summary["record_count"] == 2
    assert summary["distinct_request_keys"] == 2
    # Now ask about a request we DON'T have.
    missing_request = {
        "module_id": "fetch.world_bank",
        "family": "v2.data.country_indicator",
        "params": {"format": "json", "country": "MX"},
        "source_url": "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL",
    }
    missing = _status_for_request(workspace, "fetch.world_bank", missing_request, None)
    assert missing["status"] == "missing"
    assert missing["missing_units"] == 1
    # The cached US request still reports cached.
    cached_request = dict(missing_request)
    cached_request["params"] = {"format": "json", "country": "US"}
    cached = _status_for_request(workspace, "fetch.world_bank", cached_request, None)
    assert cached["status"] == "cached"
    # Partial coverage = some hits + some misses across the user's requested units.
    requested = [cached, missing]
    cached_units = sum(r["cached_units"] for r in requested)
    missing_units = sum(r["missing_units"] for r in requested)
    assert cached_units == 1
    assert missing_units == 1


def test_run_status_is_success_empty_when_module_returns_no_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_workspace(tmp_path)
    # World Bank returns metadata + an empty rows list — module sees zero rows.
    monkeypatch.setattr(
        "sancho.runtime.http.HttpClient.request_json",
        lambda self, method, url, params=None, headers=None, json_body=None:
            [{"page": 1, "pages": 1}, []],
    )
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({
        "base": "v2", "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
        "params": {"format": "json"},
    }), encoding="utf-8")
    rc = main(["run", "fetch.world_bank", "--workspace", str(tmp_path), "--input", str(input_file)])
    assert rc == 0
    runs_jsonl = tmp_path / WORKSPACE_DIRNAME / "logs" / "runs.jsonl"
    events = [json.loads(line) for line in runs_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    finished = [e for e in events if e["event_type"] == "run_finished"]
    assert finished[-1]["status"] == "success_empty"
    assert finished[-1]["row_count"] in (0, None)


# ---------------------------------------------------------------------------
# Ticket 12.3 — Project export manifest includes source-cache links + assumptions
# ---------------------------------------------------------------------------


def test_export_manifest_includes_source_cache_links_and_canonical_paths(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    _seed_record(workspace, {"format": "json"})
    fetched_root = workspace / "fetched-data"
    record_dirs = [
        d for d in fetched_root.rglob("data.json")
    ]
    assert record_dirs, "expected a cached record"
    record_dir = record_dirs[0].parent
    project = tmp_path / "downstream-project"
    result = export_record_to_project(
        record_dir=record_dir,
        project_root=project,
        workspace_root=workspace,
        label="phase12-test",
    )
    links = yaml.safe_load((result.bundle_dir / "source-cache-links.yml").read_text(encoding="utf-8"))
    assert links["workspace_root"] == str(workspace)
    assert links["records"]
    canonical_data = links["records"][0]["data_file"]
    assert canonical_data.endswith("data.json")
    assert str(record_dir) in canonical_data
    manifest = yaml.safe_load((result.bundle_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["records"][0]["canonical_record_dir"] == str(record_dir)
    assert manifest["sancho_workspace"] == str(workspace)
    readme = (result.bundle_dir / "README.md").read_text(encoding="utf-8")
    # README explains re-use vs re-fetch (the "assumptions" surface for the bundle).
    assert "Re-use" in readme or "Re-used" in readme
    assert "Canonical" in readme or "canonical" in readme


# ---------------------------------------------------------------------------
# Ticket 12.4 — log tail --errors works cross-platform
# ---------------------------------------------------------------------------


def test_log_tail_errors_returns_only_failed_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)

    def boom(self, method, url, params=None, headers=None, json_body=None):
        raise RuntimeError("planned upstream failure")
    monkeypatch.setattr("sancho.runtime.http.HttpClient.request_json", boom)

    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({
        "base": "v2", "method": "GET",
        "path": "/country/all/indicator/SP.POP.TOTL",
    }), encoding="utf-8")
    main(["run", "fetch.world_bank", "--workspace", str(tmp_path), "--input", str(input_file)])
    capsys.readouterr()
    rc = main(["log", "tail", "--errors", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    events = json.loads(capsys.readouterr().out)
    assert events
    statuses = {e.get("status") for e in events}
    # Every event in --errors output must be a failure variant.
    assert statuses <= {"failed", "skipped_needs_key"}
    # Always contains the module id of the failure.
    assert all(e.get("module_id") == "fetch.world_bank" for e in events)


# ---------------------------------------------------------------------------
# Ticket 12.5 — Update safety (non-mutation + personal-path immunity)
# ---------------------------------------------------------------------------


def _read_all_paths(root: Path) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_file():
            try:
                snap[str(path.relative_to(root))] = path.read_bytes()
            except OSError:
                continue
    return snap


def test_update_check_is_non_mutating(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    before = _read_all_paths(workspace)
    payload = check_updates(workspace)
    after = _read_all_paths(workspace)
    assert before == after
    assert payload["module_count"] >= 1


def test_update_preview_is_non_mutating(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    before = _read_all_paths(workspace)
    rows = preview_updates_rich(workspace)
    after = _read_all_paths(workspace)
    assert before == after
    for row in rows:
        assert row["personal_paths_touched"] == []


def test_update_apply_never_touches_personal_or_generated_paths(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Seed personal/generated files with sentinel content.
    sentinels = {
        workspace / "custom" / "fetch" / "my_custom.py": b"CUSTOM_SENTINEL",
        workspace / "playbooks" / "play.yaml": b"PLAYBOOK_SENTINEL",
        workspace / "fetched-data" / "do_not_touch.txt": b"FETCHED_DATA_SENTINEL",
        workspace / "logs" / "user_log.txt": b"LOG_SENTINEL",
        workspace / "analysis-data" / "work.txt": b"ANALYSIS_SENTINEL",
        workspace / "outputs" / "report.txt": b"OUTPUT_SENTINEL",
        workspace / ".env": b"FRED_API_KEY=do-not-touch",
        workspace / "AI_INSTRUCTIONS.md": b"USER_AI_INSTRUCTIONS_SENTINEL",
        workspace / "DATASET_CATALOG.md": b"USER_CATALOG_SENTINEL",
    }
    for path, value in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    apply_updates_safe(workspace)

    for path, expected in sentinels.items():
        assert path.read_bytes() == expected, f"update apply touched personal path: {path}"


def test_update_apply_skips_custom_overrides(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Install a custom override that shadows the source module.
    custom = workspace / "custom" / "fetch" / "fetch_world_bank"
    custom.mkdir(parents=True)
    (custom / "module.yaml").write_text(
        "id: fetch.world_bank\nversion: 9.9.9\ntype: fetch\nentrypoint: main.py:run\n"
        "catalog_tier: large\nmanaged_paths:\n  - module.yaml\n",
        encoding="utf-8",
    )
    sentinel = b"DO_NOT_OVERWRITE_CUSTOM"
    (custom / "main.py").write_bytes(b"def run(context, payload):\n    return None\n# " + sentinel + b"\n")

    apply_updates_safe(workspace)

    # Custom override file untouched.
    assert sentinel in (custom / "main.py").read_bytes()
    # And preview reported custom_override_active for this module.
    rows = preview_updates_rich(workspace)
    wb = next(r for r in rows if r["module_id"] == "fetch.world_bank")
    assert wb["status"] == "custom_override_active"


def test_update_rollback_only_touches_managed_files(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Personal sentinels (must survive rollback).
    sentinels = {
        workspace / "custom" / "fetch" / "x.py": b"X",
        workspace / "fetched-data" / "y.txt": b"Y",
        workspace / "logs" / "z.txt": b"Z",
        workspace / ".env": b"K=V",
    }
    for path, value in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    result = apply_updates_safe(workspace)
    # Mutate one personal file post-apply to confirm rollback doesn't undo it.
    (workspace / "custom" / "fetch" / "x.py").write_bytes(b"X_AFTER_APPLY")

    rollback_update(workspace, result.backup_id)

    # Source restored (it never got mutated in this scenario), personal files
    # left as-is.
    assert (workspace / "custom" / "fetch" / "x.py").read_bytes() == b"X_AFTER_APPLY"
    assert (workspace / "fetched-data" / "y.txt").read_bytes() == b"Y"
    assert (workspace / "logs" / "z.txt").read_bytes() == b"Z"
    assert (workspace / ".env").read_bytes() == b"K=V"
