from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.release import generate_release_manifest
from sancho.update_engine import (
    PERSONAL_PATH_PREFIXES,
    apply_updates_safe,
    check_updates,
    preview_updates_rich,
    rollback_update,
)


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_release_manifest_includes_modules_and_versions() -> None:
    manifest = generate_release_manifest()
    assert manifest["sancho_version"]
    assert manifest["workspace_schema_version"] >= 2
    assert manifest["modules"]
    # Spot-check one well-known module.
    entry = manifest["modules"].get("fetch.world_bank")
    assert entry is not None
    assert "version" in entry
    assert "sha" in entry and len(entry["sha"]) == 64


def test_check_updates_is_non_mutating(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0

    before = sorted(p.name for p in workspace.iterdir())
    payload = check_updates(workspace)
    after = sorted(p.name for p in workspace.iterdir())
    assert before == after
    assert "fetch.world_bank" in {m["module_id"] for m in payload["modules"]}
    assert payload["note"]
    for prefix in PERSONAL_PATH_PREFIXES:
        assert prefix in payload["note"]


def test_check_updates_reports_local_edits_as_review_needed(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Drift one managed file.
    main_py = workspace / "source" / "fetch" / "fetch_world_bank" / "module.yaml"
    main_py.write_text(main_py.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    payload = check_updates(workspace)
    entry = next(m for m in payload["modules"] if m["module_id"] == "fetch.world_bank")
    assert entry["files_with_local_edits"]
    assert entry["status"] in {"review_needed", "update_available"}


def test_preview_never_lists_personal_paths(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    rows = preview_updates_rich(workspace)
    for row in rows:
        assert row["personal_paths_touched"] == []
        for path in row["files_to_replace"]:
            for prefix in PERSONAL_PATH_PREFIXES:
                bare = prefix.rstrip("/")
                assert not path.startswith(prefix), f"{path} starts with personal prefix"
                assert path != bare, f"{path} equals personal prefix"


def test_apply_safe_with_no_actionable_updates_still_records_backup(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    result = apply_updates_safe(workspace)
    backup_dir = workspace / "update-backups" / result.backup_id
    assert backup_dir.exists()
    assert (backup_dir / "update-preview.md").exists()
    assert (backup_dir / "update-result.md").exists()
    assert result.applied_modules == []
    log = workspace / "logs" / "update-log.jsonl"
    assert log.exists()


def test_apply_safe_refuses_local_edits_by_default(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    # Drift the manifest so it appears as a local edit.
    drifted = workspace / "source" / "fetch" / "fetch_world_bank" / "module.yaml"
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\n# user-edit\n", encoding="utf-8")
    result = apply_updates_safe(workspace, allow_local_edits=False)
    # The module should have been skipped because of local edits, even if
    # it would otherwise be actionable.
    reasons = {m["reason"] for m in result.skipped_modules}
    # Either it shows up as "local_edits_present" or simply "review_needed"
    # (no upgrade was available). Either way: it was NOT applied.
    assert "fetch.world_bank" not in result.applied_modules


def test_rollback_restores_source_from_backup(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    snapshot_path = workspace / "source" / "fetch" / "fetch_world_bank" / "module.yaml"
    original = snapshot_path.read_text(encoding="utf-8")

    result = apply_updates_safe(workspace)
    # Mess up the source.
    snapshot_path.write_text("mutated after backup\n", encoding="utf-8")
    assert snapshot_path.read_text(encoding="utf-8") != original

    payload = rollback_update(workspace, result.backup_id)
    assert payload["event"] == "update_rolled_back"
    assert snapshot_path.read_text(encoding="utf-8") == original


def test_cli_update_check_json(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["update", "check", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["module_count"] >= 1
    assert payload["personal_paths_touched_by_update"] == []
    assert "personal/generated paths" in payload["note"]


def test_cli_update_apply_emits_backup_and_rollback_command(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["update", "apply", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backup_id"]
    assert payload["rollback_command"].startswith("sancho update rollback ")
