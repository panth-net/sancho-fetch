from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.client_integrations import (
    ClientResult,
    CodexAdapter,
    canonical_launch_definition,
    client_adapters,
)
from sancho.constants import WORKSPACE_DIRNAME
from sancho.install_state import (
    InstallStateError,
    ensure_workspace_identity,
    install_state_path,
    read_workspace_identity,
    state_lock,
)
from sancho.library import read_library_record
from sancho.workspace import initialize_workspace


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        "sancho.cli_setup.direct_stdio_handshake",
        lambda launch: ClientResult("sancho-mcp", "launch_verified", "stub handshake passed"),
    )
    return home


def _setup(path: Path, capsys: pytest.CaptureFixture, *extra: str) -> dict:
    rc = main(
        [
            "setup",
            "--path",
            str(path),
            "--skip-smoke-check",
            "--no-client-config",
            "--json",
            *extra,
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    return payload


def test_workspace_identity_is_persistent_and_corruption_fails_closed(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path, WORKSPACE_DIRNAME, "operator")
    first = ensure_workspace_identity(workspace)
    second = ensure_workspace_identity(workspace)
    assert first["workspace_id"] == second["workspace_id"]
    identity_path = workspace / ".sancho-workspace.json"
    identity_path.write_text("not json", encoding="utf-8")
    with pytest.raises(InstallStateError):
        ensure_workspace_identity(workspace)


def test_extension_mode_refuses_legacy_workspace_before_mutation(tmp_path: Path) -> None:
    legacy = tmp_path / WORKSPACE_DIRNAME
    legacy.mkdir()
    sentinel = legacy / "personal.txt"
    sentinel.write_bytes(b"keep exactly\n")
    before = sorted(path.name for path in legacy.iterdir())
    with pytest.raises(RuntimeError, match="matching Sancho CLI setup"):
        initialize_workspace(
            tmp_path,
            WORKSPACE_DIRNAME,
            "operator",
            allow_identity_migration=False,
        )
    assert sentinel.read_bytes() == b"keep exactly\n"
    assert sorted(path.name for path in legacy.iterdir()) == before


def test_bare_setup_reuses_registered_workspace_and_switch_requires_intent(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    first = tmp_path / "First & Library"
    second = tmp_path / "Second Library"
    first.mkdir()
    second.mkdir()
    _setup(first, capsys)
    original_id = read_workspace_identity(first / WORKSPACE_DIRNAME)["workspace_id"]

    monkeypatch.chdir(second)
    rc = main(["setup", "--skip-smoke-check", "--no-client-config", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert Path(payload["workspace_root"]) == (first / WORKSPACE_DIRNAME).resolve()

    rc = main(
        [
            "setup",
            "--path",
            str(second),
            "--skip-smoke-check",
            "--no-client-config",
            "--json",
        ]
    )
    refused = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert refused["error_code"] == "workspace_switch_requires_intent"
    assert read_library_record().primary_repo.resolve() == first.resolve()  # type: ignore[union-attr]

    switched = _setup(second, capsys, "--switch-workspace")
    assert Path(switched["workspace_root"]) == (second / WORKSPACE_DIRNAME).resolve()
    assert read_library_record().primary_repo.resolve() == second.resolve()  # type: ignore[union-attr]
    assert read_workspace_identity(second / WORKSPACE_DIRNAME)["workspace_id"] != original_id


def test_same_path_replacement_is_not_silently_adopted(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    first = _setup(project, capsys)
    original = Path(first["workspace_root"])
    original_id = read_workspace_identity(original)["workspace_id"]
    original.rename(project / "old-workspace-preserved")
    replacement = initialize_workspace(project, WORKSPACE_DIRNAME, "operator")
    assert read_workspace_identity(replacement)["workspace_id"] != original_id

    rc = main(["setup", "--skip-smoke-check", "--no-client-config", "--json"])
    refused = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert refused["error_code"] == "workspace_identity_mismatch"

    adopted = _setup(project, capsys, "--switch-workspace")
    assert Path(adopted["workspace_root"]) == replacement.resolve()
    assert (project / "old-workspace-preserved").exists()


def test_moved_workspace_keeps_identity_with_explicit_switch(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    setup = _setup(first, capsys)
    workspace = Path(setup["workspace_root"])
    workspace_id = read_workspace_identity(workspace)["workspace_id"]
    moved = second / WORKSPACE_DIRNAME
    workspace.rename(moved)

    rc = main(["setup", "--skip-smoke-check", "--no-client-config", "--json"])
    refused = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert refused["error_code"] == "stale_workspace_requires_path"

    # A stale registration is still a registration: --path alone must not
    # silently re-point it either.
    rc = main(
        ["setup", "--path", str(second), "--skip-smoke-check", "--no-client-config", "--json"]
    )
    refused_with_path = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert refused_with_path["error_code"] == "stale_workspace_requires_path"
    assert read_library_record().primary_repo.resolve() == first.resolve()

    switched = _setup(second, capsys, "--switch-workspace")
    assert Path(switched["workspace_root"]) == moved.resolve()
    assert read_workspace_identity(moved)["workspace_id"] == workspace_id


def test_unowned_skill_and_corrupt_state_are_preserved(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    personal = isolated_home / ".agents" / "skills" / "sancho" / "SKILL.md"
    personal.parent.mkdir(parents=True)
    personal.write_text("my personal skill\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    payload = _setup(project, capsys)
    skill_step = next(step for step in payload["steps"] if step["name"] == "skills")
    assert skill_step["status"] == "warn"
    assert skill_step["user_action_required"] is True
    assert personal.read_text(encoding="utf-8") == "my personal skill\n"

    install_state_path().write_text("{broken", encoding="utf-8")
    before = personal.read_bytes()
    rc = main(["setup", "--skip-smoke-check", "--no-client-config", "--json"])
    failed = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert failed["error_code"] == "ownership_state_untrusted"
    assert personal.read_bytes() == before


def test_cursor_adapter_preserves_collision_drift_and_unrelated_settings(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sancho.client_integrations.platform.system", lambda: "Linux")
    workspace = initialize_workspace(tmp_path / "repo", WORKSPACE_DIRNAME, "operator")
    launch = canonical_launch_definition(workspace)
    config_path = isolated_home / ".cursor" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"theme": "mine", "mcpServers": {"sancho": {"command": "mine"}}}),
        encoding="utf-8",
    )
    adapter = client_adapters(launch)["cursor"]

    collision = adapter.apply(launch)
    assert collision.state == "user_action_required"
    assert json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["sancho"] == {"command": "mine"}

    adopted = adapter.apply(launch, replace_unowned=True)
    assert adopted.changed is True
    configured = json.loads(config_path.read_text(encoding="utf-8"))
    assert configured["theme"] == "mine"
    assert configured["mcpServers"]["sancho"]["type"] == "stdio"

    configured["mcpServers"]["sancho"]["args"].append("--personal-edit")
    config_path.write_text(json.dumps(configured), encoding="utf-8")
    assert adapter.repair(launch).state == "preserved_drift"
    assert adapter.remove(launch).state == "preserved_drift"
    assert "--personal-edit" in json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["sancho"]["args"]


def test_default_uninstall_preserves_workspace_and_env_byte_for_byte(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    payload = _setup(project, capsys)
    workspace = Path(payload["workspace_root"])
    env_path = workspace / ".env"
    env_path.write_bytes(b"PRIVATE_KEY=do-not-touch\n")
    before = env_path.read_bytes()

    rc = main(["uninstall", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert workspace.exists()
    assert env_path.read_bytes() == before
    assert result["workspaces_removed"] == []
    assert any(item["kind"] == "data-bearing-workspace" for item in result["preserved"])
    assert result["package_uninstall_command"] == "uv tool uninstall sancho-fetch"


def test_exact_purge_cannot_delete_sibling_workspace(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    first = initialize_workspace(tmp_path / "one", WORKSPACE_DIRNAME, "operator")
    sibling = initialize_workspace(tmp_path / "two", WORKSPACE_DIRNAME, "operator")
    workspace_id = read_workspace_identity(first)["workspace_id"]
    rc = main(
        [
            "uninstall",
            "--purge-workspace",
            "--workspace",
            str(first),
            "--workspace-id",
            workspace_id,
            "--yes",
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert rc == 0, result
    assert not first.exists()
    assert sibling.exists()


def test_downloads_require_a_separate_exact_purge(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace = initialize_workspace(tmp_path / "project", WORKSPACE_DIRNAME, "operator")
    downloads = tmp_path / "project" / "sancho-downloads"
    downloads.mkdir()
    (downloads / "result.csv").write_bytes(b"a,b\n1,2\n")
    rc = main(["uninstall", "--purge-downloads", str(downloads), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    assert workspace.exists()
    assert not downloads.exists()
    assert payload["workspaces_removed"] == []


def test_vscode_profile_status_and_uninstall_ignore_other_profiles(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr("sancho.client_integrations.platform.system", lambda: "Linux")
    workspace = initialize_workspace(tmp_path / "repo", WORKSPACE_DIRNAME, "operator")
    launch = canonical_launch_definition(workspace)
    selected = isolated_home / ".config" / "Code" / "User" / "profiles" / "work"
    unused = isolated_home / ".config" / "Code" / "User" / "profiles" / "unused" / "mcp.json"
    unused.parent.mkdir(parents=True)
    unused.write_text(json.dumps({"servers": {"personal": {"command": "mine"}}}), encoding="utf-8")

    adapter = client_adapters(launch, vscode_config_path=selected)["vscode"]
    adapter._detected = True  # type: ignore[attr-defined]
    result = adapter.apply(launch)
    assert result.state == "restart_required"
    assert result.metadata["profile"].endswith("profiles/work/mcp.json")
    assert result.metadata["trust"] == "client_confirmation_required_before_first_launch"

    repeated = adapter.apply(launch)
    assert repeated.state == "unchanged"
    assert repeated.user_action_required is True
    assert "trust" in repeated.detail

    from sancho.cli_ready import _clients_status

    status = _clients_status(workspace)
    assert status["requested_count"] == 1
    assert status["results"][0]["state"] == "restart_required"
    assert status["results"][0]["metadata"]["profile"].endswith("profiles/work/mcp.json")

    rc = main(["uninstall", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    selected_config = selected / "mcp.json"
    assert "sancho" not in json.loads(selected_config.read_text(encoding="utf-8"))["servers"]
    assert json.loads(unused.read_text(encoding="utf-8"))["servers"]["personal"] == {"command": "mine"}


def test_concurrent_cooperating_config_writers_preserve_unrelated_values(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sancho.client_integrations.platform.system", lambda: "Linux")
    workspace = initialize_workspace(tmp_path / "repo", WORKSPACE_DIRNAME, "operator")
    launch = canonical_launch_definition(workspace)
    config_path = isolated_home / ".cursor" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"theme": "mine", "mcpServers": {}}), encoding="utf-8")
    adapter = client_adapters(launch)["cursor"]
    barrier = threading.Barrier(2)

    def unrelated_writer() -> None:
        barrier.wait()
        with state_lock(config_path):
            value = json.loads(config_path.read_text(encoding="utf-8"))
            value["unrelated"] = {"kept": True}
            from sancho.install_state import atomic_write_json

            atomic_write_json(config_path, value, sort_keys=False)

    thread = threading.Thread(target=unrelated_writer)
    thread.start()
    barrier.wait()
    installed = adapter.apply(launch)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert installed.ok
    value = json.loads(config_path.read_text(encoding="utf-8"))
    assert value["theme"] == "mine"
    assert value["unrelated"] == {"kept": True}
    assert value["mcpServers"]["sancho"]["type"] == "stdio"


def test_interrupted_atomic_client_write_preserves_original(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sancho.client_integrations.platform.system", lambda: "Linux")
    workspace = initialize_workspace(tmp_path / "repo", WORKSPACE_DIRNAME, "operator")
    launch = canonical_launch_definition(workspace)
    config_path = isolated_home / ".cursor" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    original = b'{"theme":"mine","mcpServers":{}}\n'
    config_path.write_bytes(original)
    adapter = client_adapters(launch)["cursor"]

    real_replace = __import__("os").replace

    def fail_target(source: str | Path, target: str | Path) -> None:
        if Path(target) == config_path:
            raise OSError("simulated interrupted replace")
        real_replace(source, target)

    monkeypatch.setattr("sancho.client_integrations.os.replace", fail_target)
    result = adapter.apply(launch)
    assert result.state == "failed"
    assert config_path.read_bytes() == original


def test_codex_cli_is_only_mutation_surface_and_owned_update_rolls_forward(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (isolated_home / ".codex").mkdir()
    config_toml = isolated_home / ".codex" / "config.toml"
    config_toml.write_bytes(b'# comments and unrelated settings survive\nmodel = "example"\n')
    workspace = initialize_workspace(tmp_path / "repo", WORKSPACE_DIRNAME, "operator")
    launch = canonical_launch_definition(workspace)
    current: dict[str, object] = {}
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        operation = command[2]
        if operation == "get":
            if not current:
                # Real codex-cli phrasing; _get treats anything else as an error.
                return subprocess.CompletedProcess(
                    command, 1, "", "Error: No MCP server named 'sancho' found."
                )
            payload = {
                "transport": {
                    "type": "stdio",
                    "command": current["command"],
                    "args": current["args"],
                    "env": current["env"],
                }
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        if operation == "remove":
            current.clear()
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation == "add":
            split = command.index("--")
            current.update({"command": command[split + 1], "args": command[split + 2 :], "env": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    monkeypatch.setattr("sancho.client_integrations.subprocess.run", fake_run)
    adapter = CodexAdapter(executable="codex")
    assert adapter.apply(launch).state == "configured"
    changed_launch = replace(launch, arguments=(*launch.arguments, "--sync"))
    assert adapter.apply(changed_launch).state == "configured"
    assert any(call[2] == "remove" for call in calls)
    assert config_toml.read_bytes() == b'# comments and unrelated settings survive\nmodel = "example"\n'
    assert adapter.remove(changed_launch).state == "removed"


def test_codex_transient_get_failure_fails_closed(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient `codex mcp get` failure must not read as "not configured":
    remove() would otherwise drop the ownership record and orphan a live entry."""
    (isolated_home / ".codex").mkdir()
    workspace = initialize_workspace(tmp_path / "repo", WORKSPACE_DIRNAME, "operator")
    launch = canonical_launch_definition(workspace)
    current: dict[str, object] = {}
    transient = {"active": False}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        operation = command[2]
        if operation == "get":
            if transient["active"]:
                return subprocess.CompletedProcess(command, 2, "", "connection reset")
            if not current:
                return subprocess.CompletedProcess(
                    command, 1, "", "Error: No MCP server named 'sancho' found."
                )
            payload = {
                "transport": {
                    "type": "stdio",
                    "command": current["command"],
                    "args": current["args"],
                    "env": current["env"],
                }
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        if operation == "remove":
            current.clear()
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation == "add":
            split = command.index("--")
            current.update({"command": command[split + 1], "args": command[split + 2 :], "env": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    monkeypatch.setattr("sancho.client_integrations.subprocess.run", fake_run)
    adapter = CodexAdapter(executable="codex")
    assert adapter.apply(launch).state == "configured"

    transient["active"] = True
    result = adapter.remove(launch)
    assert result.state == "failed"
    assert "codex mcp get" in result.detail
    from sancho.install_state import load_install_state

    assert isinstance(load_install_state()["clients"].get("codex"), dict), (
        "ownership record must survive a transient CLI failure"
    )
    assert current, "the live Codex entry must not be touched on failure"


def test_ready_is_read_only_and_reports_missing_sample_module(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    from sancho.cli_ready import ready_payload

    project = tmp_path / "project"
    project.mkdir()
    payload = _setup(project, capsys)  # --skip-smoke-check: no sample module
    workspace = Path(payload["workspace_root"])
    module_dir = workspace / "source" / "fetch" / "fetch_world_bank"
    assert not module_dir.exists()

    before = sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*"))
    ready = ready_payload(str(project))
    assert ready["checks"]["sample_module"]["ok"] is False
    assert "run `sancho setup`" in ready["checks"]["sample_module"]["detail"]
    assert not module_dir.exists(), "ready must diagnose, never install"
    after = sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*"))
    assert after == before, "ready must not create or remove workspace files"


def test_uninstall_still_works_after_purging_the_active_workspace(
    tmp_path: Path,
    isolated_home: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """--purge-workspace clears the active workspace record; a later plain
    uninstall must still detach owned skills/clients instead of dead-ending."""
    project = tmp_path / "project"
    project.mkdir()
    payload = _setup(project, capsys)
    workspace = Path(payload["workspace_root"])
    workspace_id = read_workspace_identity(workspace)["workspace_id"]

    rc = main(
        [
            "uninstall",
            "--purge-workspace",
            "--workspace",
            str(workspace),
            "--workspace-id",
            workspace_id,
            "--yes",
            "--json",
        ]
    )
    purged = json.loads(capsys.readouterr().out)
    assert rc == 0, purged
    assert not workspace.exists()

    rc = main(["uninstall", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert rc == 0, result
    assert result["status"] != "failed"
    assert not any(
        "no active workspace" in item.get("detail", "") for item in result["failed"]
    )
