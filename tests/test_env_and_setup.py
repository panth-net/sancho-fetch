from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.cli_env import MODULE_KEYS, provider_key_hints
from sancho.constants import WORKSPACE_DIRNAME
from sancho.runtime.executor import run_module


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def _write_env_probe_module(workspace: Path) -> None:
    module_dir = workspace / "source" / "fetch" / "fetch_env_probe"
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.yaml").write_text(
        "\n".join([
            "id: fetch.env_probe",
            "version: 1.0.0",
            "type: fetch",
            "catalog_tier: small",
            "entrypoint: run.py:run",
            "api_key_env: SOME_REQUIRED_API_KEY",
            "managed_paths:",
            "  - module.yaml",
            "  - run.py",
            "output_schema:",
            "  type: object",
            "  required:",
            "    - rows",
            "",
        ]),
        encoding="utf-8",
    )
    (module_dir / "run.py").write_text(
        "def run(context, payload):\n"
        "    return {'rows': [{'key': context.env.get('SOME_REQUIRED_API_KEY')}]} \n",
        encoding="utf-8",
    )


def test_provider_key_hints_resolves_short_provider() -> None:
    hints = provider_key_hints("census")
    ids = {h["module_id"] for h in hints}
    assert "fetch.census.acs_profile" in ids
    for hint in hints:
        for key in hint["env_keys"]:
            assert key.endswith("_KEY") or key.endswith("_TOKEN") or key.endswith("_EMAIL") or key.endswith("_SECRET") or key.endswith("_ID")


def test_provider_key_hints_resolves_full_module_id() -> None:
    hints = provider_key_hints("fetch.fred.series")
    assert any(h["module_id"] == "fetch.fred.series" for h in hints)
    assert any("FRED_API_KEY" in h["env_keys"] for h in hints)


def test_provider_key_hints_empty_for_unknown_provider() -> None:
    assert provider_key_hints("xyzqq_no_such_thing") == []


def test_env_check_reports_missing_keys(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("FRED_API_KEY=anything\n", encoding="utf-8")
    capsys.readouterr()
    rc = main(["env", "check", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # FRED is now "ready".
    fred = next(p for p in payload["providers"] if p["module_id"] == "fetch.fred.series")
    assert fred["ready"] is True
    # CENSUS still needs CENSUS_API_KEY.
    census = next(p for p in payload["providers"] if p["module_id"] == "fetch.census.acs_profile")
    assert census["ready"] is False
    assert "CENSUS_API_KEY" in census["missing"]


def test_env_check_uses_project_env_as_fallback(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _init_workspace(tmp_path)
    (tmp_path / ".env").write_text("FRED_API_KEY=anything\n", encoding="utf-8")
    capsys.readouterr()

    rc = main(["env", "check", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    fred = next(p for p in payload["providers"] if p["module_id"] == "fetch.fred.series")
    assert fred["ready"] is True
    assert payload["env_path"] == str(tmp_path / ".env")
    checked = {row["path"] for row in payload["env_paths"]}
    assert str(tmp_path / ".env") in checked
    assert str(tmp_path / WORKSPACE_DIRNAME / ".env") in checked


def test_workspace_env_overrides_project_env_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    (tmp_path / ".env").write_text("FRED_API_KEY=project-value\n", encoding="utf-8")
    (workspace / ".env").write_text("FRED_API_KEY=workspace-value\n", encoding="utf-8")
    capsys.readouterr()

    rc = main(["env", "check", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["shadowed_keys"] == ["FRED_API_KEY"]
    assert "project-value" not in json.dumps(payload)
    assert "workspace-value" not in json.dumps(payload)


def test_run_module_loads_project_env_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _init_workspace(tmp_path)
    _write_env_probe_module(workspace)
    (tmp_path / ".env").write_text("SOME_REQUIRED_API_KEY=project-value\n", encoding="utf-8")
    (workspace / ".env").write_text("SANCHO_DEVELOPER_MODE=false\n", encoding="utf-8")
    monkeypatch.delenv("SOME_REQUIRED_API_KEY", raising=False)

    result = run_module(workspace, "fetch.env_probe", {})

    assert result.output["rows"] == [{"key": "project-value"}]


def test_run_module_workspace_env_overrides_project_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _init_workspace(tmp_path)
    _write_env_probe_module(workspace)
    (tmp_path / ".env").write_text("SOME_REQUIRED_API_KEY=project-value\n", encoding="utf-8")
    (workspace / ".env").write_text("SOME_REQUIRED_API_KEY=workspace-value\n", encoding="utf-8")
    monkeypatch.delenv("SOME_REQUIRED_API_KEY", raising=False)

    result = run_module(workspace, "fetch.env_probe", {})

    assert result.output["rows"] == [{"key": "workspace-value"}]


def test_env_check_never_reports_values(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    secret = "extremely-secret-value-xyzqq"
    (workspace / ".env").write_text(f"FRED_API_KEY={secret}\n", encoding="utf-8")
    capsys.readouterr()
    rc = main(["env", "check", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    output = capsys.readouterr().out
    assert secret not in output
    # The key NAME should appear.
    assert "FRED_API_KEY" in output


def test_env_open_creates_env_file_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").unlink(missing_ok=True)
    # Stub the editor opener so we don't actually launch anything.
    monkeypatch.setattr("sancho.cli_env._open_in_editor", lambda path: None)
    rc = main(["env", "open", "census", "--workspace", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / ".env").exists()
    out = capsys.readouterr().out
    assert "CENSUS_API_KEY" in out


def test_sancho_setup_no_network_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    capsys.readouterr()
    rc = main([
        "setup",
        "--path", str(tmp_path),
        "--no-network",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    step_names = {s["name"] for s in payload["steps"]}
    assert {"python", "uv", "node", "workspace", "library_register", "skills", "mcp_config"} <= step_names
    # Python check should be OK on Python 3.11+
    python_step = next(s for s in payload["steps"] if s["name"] == "python")
    assert python_step["status"] == "ok"
    # Workspace created.
    assert payload["workspace_root"]
    assert Path(payload["workspace_root"]).exists()
    # Library pointer at the fake home.
    assert payload["library_pointer"]
    assert str(fake_home) in payload["library_pointer"]
    assert payload["skills_installed_count"] >= 4
    assert len(payload["mcp_configs_written"]) == 3
    assert payload["claude_desktop_config_installed"] is None


def test_sancho_setup_skip_smoke_check_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    capsys.readouterr()
    rc = main([
        "setup",
        "--path", str(tmp_path),
        "--skip-smoke-check",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    step_names = {s["name"] for s in payload["steps"]}
    assert "smoke" not in step_names
    assert "ready" not in step_names
    assert payload["has_failures"] is False


def test_sancho_setup_json_with_smoke_test_is_json_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    capsys.readouterr()

    rc = main([
        "setup",
        "--path", str(tmp_path),
        "--json",
    ])

    assert rc == 0
    output = capsys.readouterr().out
    assert output.lstrip().startswith("{")
    assert "Installed module" not in output
    payload = json.loads(output)
    smoke_step = next(s for s in payload["steps"] if s["name"] == "smoke")
    assert smoke_step["status"] == "ok"
    assert "fetch.world_bank installed" in smoke_step["detail"]
    ready_step = next(s for s in payload["steps"] if s["name"] == "ready")
    assert ready_step["status"] == "ok"
    assert payload["ready"]["ready"] is True


def test_sancho_ready_json_after_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert main(["setup", "--path", str(tmp_path), "--json"]) == 0
    capsys.readouterr()

    rc = main(["ready", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] is True
    assert payload["checks"]["workspace"]["ok"] is True
    assert payload["checks"]["library_pointer"]["ok"] is True
    assert payload["checks"]["skills"]["ok"] is True
    assert payload["checks"]["mcp_snippets"]["ok"] is True
    assert payload["checks"]["sample_module"]["ok"] is True


def test_sancho_setup_registration_failure_is_fatal_and_gates_skills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    def boom(repo: Path):
        _ = repo
        raise RuntimeError("cannot write library pointer")

    monkeypatch.setattr("sancho.cli_setup.register_library", boom)
    capsys.readouterr()

    rc = main(["setup", "--path", str(tmp_path), "--skip-smoke-check", "--json"])

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_failures"] is True
    assert payload["failed_step"] == "library_register"
    assert payload["error_code"] == "library_register_failed"
    assert payload["skills_installed_count"] == 0
    assert not (fake_home / ".claude" / "skills" / "sancho" / "SKILL.md").exists()


def test_add_reports_not_ready_catalog_missing_without_clean_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _init_workspace(tmp_path)
    from sancho.modules import ModuleInstallResult

    def fake_install_target(*args, **kwargs):
        _ = args, kwargs
        return [
            ModuleInstallResult(
                module_id="fetch.large",
                install_path=tmp_path / "sancho-workspace" / "source" / "fetch" / "fetch_large",
                catalog_state="not_ready_catalog_missing",
                detail="large-tier provider requires catalog.json",
            )
        ]

    monkeypatch.setattr("sancho.cli_workspace_commands.install_target", fake_install_target)
    capsys.readouterr()

    rc = main(["add", "fetch.large", "--workspace", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Installed module" not in captured.out
    assert "not ready" in captured.err
    assert "catalog.json" in captured.err


def test_doctor_json_reports_workspace_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    capsys.readouterr()

    rc = main(["doctor", "--workspace", str(empty_project), "--json"])

    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["error_code"] == "workspace_not_found"
    assert payload["failed_step"] == "doctor"
    assert payload["safe_retry"].startswith("sancho setup")



def test_sancho_setup_can_install_claude_desktop_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr("sancho.mcp.config.sys.platform", "win32")
    capsys.readouterr()
    rc = main(
        [
            "setup",
            "--path",
            str(tmp_path),
            "--no-network",
            "--install-claude-desktop",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    expected_config = fake_home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    assert Path(payload["claude_desktop_config_installed"]) == expected_config
    config = json.loads(expected_config.read_text(encoding="utf-8"))
    server = config["mcpServers"]["sancho"]
    assert Path(server["command"]).name.lower().startswith("sancho")
    assert server["args"][:2] == ["mcp", "serve"]
    workspace_index = server["args"].index("--workspace") + 1
    assert Path(server["args"][workspace_index]) == tmp_path / WORKSPACE_DIRNAME
    assert server["args"][-2:] == ["--transport", "stdio"]
    claude_step = next(s for s in payload["steps"] if s["name"] == "claude_desktop_config")
    assert claude_step["status"] == "ok"


def test_claude_desktop_config_uses_appdata_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sancho.mcp.config import claude_desktop_config_path

    roaming = tmp_path / "RoamingProfile"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setattr("sancho.mcp.config.sys.platform", "win32")

    assert claude_desktop_config_path() == roaming / "Claude" / "claude_desktop_config.json"


def test_sancho_setup_install_claude_desktop_is_nonfatal_on_linux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr("sancho.mcp.config.sys.platform", "linux")
    capsys.readouterr()
    rc = main(
        [
            "setup",
            "--path",
            str(tmp_path),
            "--no-network",
            "--install-claude-desktop",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_failures"] is False
    assert payload["claude_desktop_config_installed"] is None
    assert len(payload["mcp_configs_written"]) == 3
    claude_step = next(s for s in payload["steps"] if s["name"] == "claude_desktop_config")
    assert claude_step["status"] == "warn"
    assert "Windows and macOS" in claude_step["detail"]


def test_installer_scripts_are_present_and_executable_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    installer_dir = root / "installers"
    for name in ("setup.sh", "setup.bat", "Install Sancho.command", "Install Sancho.bat"):
        path = installer_dir / name
        assert path.exists(), f"missing installer: {name}"
        # Sanity: file is non-empty.
        assert path.stat().st_size > 0


def test_installers_use_uv_python_resolution_and_visible_failures() -> None:
    root = Path(__file__).resolve().parents[1]
    setup_sh = (root / "installers" / "setup.sh").read_text(encoding="utf-8")
    setup_bat = (root / "installers" / "setup.bat").read_text(encoding="utf-8")
    command = (root / "installers" / "Install Sancho.command").read_text(encoding="utf-8")

    assert "set -euo pipefail" in setup_sh
    assert "command -v curl" in setup_sh
    assert "uv tool install ." in setup_sh
    assert "uv tool uninstall sancho-fetch" in setup_sh
    assert "uv python install 3.11" not in setup_sh
    assert "--python 3.11" not in setup_sh
    assert "--force" not in setup_sh
    assert "uv tool install ." in setup_bat
    assert "uv tool uninstall sancho-fetch" in setup_bat
    assert "uv python install 3.11" not in setup_bat
    assert "--python 3.11" not in setup_bat
    assert "--force" not in setup_bat
    assert "enabledelayedexpansion" not in setup_bat.lower()
    assert "where python" not in setup_bat.lower()
    assert "EXITCODE=$?" in command
    assert "Press Return to close this window." in command
