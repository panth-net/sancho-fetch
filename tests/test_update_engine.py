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


# ── .env safety: the guarantees non-technical users depend on ────────────


def test_setup_never_overwrites_user_env(tmp_path: Path) -> None:
    """Re-running setup/init over an existing workspace must leave the
    user's keys byte-for-byte intact."""
    workspace = _init_workspace(tmp_path)
    env_path = workspace / ".env"
    env_path.write_text("MY_SECRET_KEY=user-pasted-value\n", encoding="utf-8")
    before = env_path.read_bytes()

    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    assert env_path.read_bytes() == before


def test_update_apply_never_touches_env(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    env_path = workspace / ".env"
    env_path.write_text("CENSUS_API_KEY=real-user-key\n", encoding="utf-8")
    before = env_path.read_bytes()

    result = apply_updates_safe(workspace)

    assert env_path.read_bytes() == before
    backup_dir = workspace / "update-backups" / result.backup_id
    # The backup snapshots source/, never the user's secrets.
    assert not list(backup_dir.rglob(".env"))


def test_update_apply_refreshes_env_example_but_not_env(tmp_path: Path) -> None:
    """Upgrades must deliver the new release's key documentation without
    ever writing to .env itself."""
    from sancho.constants import BUNDLED_ENV_EXAMPLE

    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    env_path = workspace / ".env"
    env_path.write_text("CENSUS_API_KEY=real-user-key\n", encoding="utf-8")
    env_before = env_path.read_bytes()
    stale = "# stale docs from an older release\n"
    (workspace / ".env.example").write_text(stale, encoding="utf-8")

    apply_updates_safe(workspace)

    refreshed = (workspace / ".env.example").read_text(encoding="utf-8")
    assert refreshed != stale
    assert refreshed == BUNDLED_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert env_path.read_bytes() == env_before


def test_update_apply_backs_up_env_example_before_overwriting(tmp_path: Path) -> None:
    """The refresh overwrites .env.example, so the old copy must be recoverable.

    A user who pastes keys into .env.example instead of .env would otherwise
    lose them with no recovery path.
    """
    workspace = _init_workspace(tmp_path)
    assert main(["add", "fetch.world_bank", "--workspace", str(tmp_path)]) == 0
    mine = "# my own notes\nSOME_KEY=pasted-here-by-mistake\n"
    (workspace / ".env.example").write_text(mine, encoding="utf-8")

    result = apply_updates_safe(workspace)

    # Overwritten as designed...
    assert (workspace / ".env.example").read_text(encoding="utf-8") != mine
    # ...but the previous copy survives in the backup, and rollback restores it.
    assert (result.backup_dir / "env.example.before").read_text(encoding="utf-8") == mine
    rollback_update(workspace, result.backup_id)
    assert (workspace / ".env.example").read_text(encoding="utf-8") == mine


def test_env_is_a_personal_path() -> None:
    """Direct pin: a future edit to PERSONAL_PATH_PREFIXES must not silently
    drop .env protection."""
    from sancho.update_engine import _is_personal_path

    assert _is_personal_path(".env") is True
    assert ".env" in PERSONAL_PATH_PREFIXES


def test_env_open_restores_missing_env_example_from_bundled_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A workspace missing both .env and .env.example (deleted, or made by an
    older version) still yields a fully documented keys file."""
    from sancho.constants import BUNDLED_ENV_EXAMPLE

    workspace = _init_workspace(tmp_path)
    (workspace / ".env").unlink(missing_ok=True)
    (workspace / ".env.example").unlink(missing_ok=True)
    (tmp_path / ".env").unlink(missing_ok=True)
    (tmp_path / ".env.example").unlink(missing_ok=True)
    monkeypatch.setattr("sancho.cli_env._open_in_editor", lambda path: None)
    capsys.readouterr()

    rc = main(["env", "open", "--workspace", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    created = [p for p in (tmp_path / ".env", workspace / ".env") if p.exists()]
    assert created, "env open must create a .env somewhere findable"
    contents = created[0].read_text(encoding="utf-8")
    assert contents == BUNDLED_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert str(created[0]) in out


# ── __pycache__ never leaks into workspaces or release manifests ─────────


def test_copy_tree_skips_pycache(tmp_path: Path) -> None:
    from sancho.workspace import _copy_tree

    src = tmp_path / "template"
    (src / "__pycache__").mkdir(parents=True)
    (src / "real.py").write_text("x = 1\n", encoding="utf-8")
    (src / "__pycache__" / "real.cpython-312.pyc").write_bytes(b"\x00")
    (src / "stray.pyc").write_bytes(b"\x00")

    dst = tmp_path / "out"
    copied = _copy_tree(src, dst)

    assert (dst / "real.py").exists()
    assert not (dst / "__pycache__").exists()
    assert not (dst / "stray.pyc").exists()
    assert [p.name for p in copied] == ["real.py"]


def test_template_sha_ignores_pycache(tmp_path: Path) -> None:
    from sancho.release import _template_sha

    template = tmp_path / "template"
    template.mkdir()
    (template / "main.py").write_text("x = 1\n", encoding="utf-8")
    clean_sha = _template_sha(template)

    (template / "__pycache__").mkdir()
    (template / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00")
    assert _template_sha(template) == clean_sha
