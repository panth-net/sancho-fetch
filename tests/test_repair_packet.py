from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.repair_packet import write_error_packet
from sancho.run_log import RunHandle


def _make_handle(tmp_path: Path) -> RunHandle:
    workspace = tmp_path / WORKSPACE_DIRNAME
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "logs" / "errors").mkdir(parents=True, exist_ok=True)
    return RunHandle(
        run_id="20260511T100000-abcdef",
        workspace_root=workspace,
        started_at=datetime.now(timezone.utc),
        module_id="fetch.world_bank",
        module_source="source",
        module_version="1.0.0",
        module_path=str(workspace / "source" / "fetch" / "fetch_world_bank" / "main.py"),
        request_summary={"base": "v2", "path": "/country/all"},
        env_names=["FRED_API_KEY"],
        current_project_path=str(tmp_path),
    )


def test_repair_packet_includes_all_phase6_sections(tmp_path: Path) -> None:
    handle = _make_handle(tmp_path)
    packet = write_error_packet(
        handle,
        error_message="Upstream returned 500",
        exception_text="Traceback (most recent call last): ...",
        http_status=500,
        response_excerpt='{"error": "internal"}',
        resolved_url="https://api.example.com/data",
        files_written=[
            "/abs/path/fetched-data/fetch.world_bank/family/key/ts/data.json",
        ],
        cache_status_before="missing",
        cache_status_after="empty_result",
        last_successful_run={
            "run_id": "20260510T100000-prev",
            "finished_at": "2026-05-10T10:00:00+00:00",
            "row_count": 42,
        },
        docs_links=["World Bank API: https://api.worldbank.org/docs"],
        suggested_override_path="/abs/custom/fetch/fetch_world_bank",
        safe_retry_command="sancho run fetch.world_bank --workspace /abs/ws",
    )
    text = packet.read_text(encoding="utf-8")
    for must_have in (
        "# Sancho run error: fetch.world_bank",
        "## What failed",
        "Upstream returned 500",
        "## HTTP",
        "status: `500`",
        "resolved_url: `https://api.example.com/data`",
        "## Provider response (truncated)",
        "## Traceback",
        "## Request",
        "## Environment keys present",
        "`FRED_API_KEY`",
        "## Files written before failure",
        "## Cache status",
        "before: missing",
        "after:  empty_result",
        "## Last successful run",
        "row_count: 42",
        "## Docs / provider links",
        "World Bank API",
        "## Suggested next steps",
        "/abs/custom/fetch/fetch_world_bank",
        "sancho run fetch.world_bank",
        "sancho repair note --run-id 20260511T100000-abcdef --module fetch.world_bank",
    ):
        assert must_have in text, f"missing section: {must_have}"


def test_repair_packet_never_contains_env_values(tmp_path: Path) -> None:
    handle = _make_handle(tmp_path)
    packet = write_error_packet(handle, error_message="failed")
    text = packet.read_text(encoding="utf-8")
    # Only the env NAME, not any value.
    assert "FRED_API_KEY" in text
    assert "Values are not recorded" in text


def test_sancho_repair_note_appends_jsonl_and_module_notes(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    workspace = tmp_path / WORKSPACE_DIRNAME
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    # Create a custom override so the CLI also writes REPAIR_NOTES.md there.
    custom = workspace / "custom" / "fetch" / "fetch_world_bank"
    custom.mkdir(parents=True)
    (custom / "module.yaml").write_text(
        "id: fetch.world_bank\nversion: 9.9.9\ntype: fetch\nentrypoint: main.py:run\n"
        "catalog_tier: large\nmanaged_paths:\n  - module.yaml\n",
        encoding="utf-8",
    )
    (custom / "main.py").write_text("def run(context, payload): return {}\n", encoding="utf-8")
    capsys.readouterr()

    rc = main([
        "repair", "note",
        "--module", "fetch.world_bank",
        "--summary", "Patched the paging param after upstream changed",
        "--run-id", "20260511T100000-abcdef",
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    jsonl = Path(payload["jsonl"])
    assert jsonl.exists()
    last = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[-1])
    assert last["module_id"] == "fetch.world_bank"
    assert last["run_id"] == "20260511T100000-abcdef"
    assert "Patched the paging param" in last["summary"]
    notes = Path(payload["module_notes"])
    assert notes.exists()
    assert "Patched the paging param" in notes.read_text(encoding="utf-8")


def test_sancho_repair_note_skips_module_notes_when_no_custom_override(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    capsys.readouterr()
    rc = main([
        "repair", "note",
        "--module", "fetch.world_bank",
        "--summary", "Just a note",
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["module_notes"] is None
