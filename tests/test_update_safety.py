from __future__ import annotations

from pathlib import Path

from sancho.cli import main
from sancho.modules import apply_updates, preview_updates


def test_update_accept_changes_only_managed_and_lock(tmp_path: Path) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    assert main(["add", "fetch.census.acs_profile", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    custom_file = workspace / "custom" / "fetch" / "business_logic.py"
    custom_file.write_text("CUSTOM=1\n", encoding="utf-8")

    managed_file = workspace / "source" / "fetch" / "fetch_census_acs_profile" / "main.py"
    managed_file.write_text(managed_file.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    actions = preview_updates(workspace)
    assert actions

    changed = apply_updates(workspace, actions)
    assert changed
    assert all(path == "modules.lock.yaml" or path.startswith("source/") for path in changed)
    assert custom_file.read_text(encoding="utf-8") == "CUSTOM=1\n"
