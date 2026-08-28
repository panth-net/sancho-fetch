from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.cli_env import MODULE_KEYS, provider_key_hints
from sancho.constants import WORKSPACE_DIRNAME
from sancho.runtime.executor import ModuleExecutionError, run_module


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


def test_env_check_ignores_project_level_env(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Sancho keeps exactly one .env, inside the workspace.

    A stray project-level .env must not silently supply keys, or users end up
    debugging two files that disagree.
    """
    _init_workspace(tmp_path)
    (tmp_path / ".env").write_text("FRED_API_KEY=anything\n", encoding="utf-8")
    capsys.readouterr()

    rc = main(["env", "check", "--workspace", str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    fred = next(p for p in payload["providers"] if p["module_id"] == "fetch.fred.series")
    assert fred["ready"] is False
    workspace_env = str(tmp_path / WORKSPACE_DIRNAME / ".env")
    assert payload["env_path"] == workspace_env
    assert {row["path"] for row in payload["env_paths"]} == {workspace_env}


def test_run_module_reads_the_workspace_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _init_workspace(tmp_path)
    _write_env_probe_module(workspace)
    (workspace / ".env").write_text("SOME_REQUIRED_API_KEY=workspace-value\n", encoding="utf-8")
    monkeypatch.delenv("SOME_REQUIRED_API_KEY", raising=False)

    result = run_module(workspace, "fetch.env_probe", {})

    assert result.output["rows"] == [{"key": "workspace-value"}]


def test_run_module_does_not_fall_back_to_a_project_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _init_workspace(tmp_path)
    _write_env_probe_module(workspace)
    (tmp_path / ".env").write_text("SOME_REQUIRED_API_KEY=project-value\n", encoding="utf-8")
    (workspace / ".env").write_text("SANCHO_DEVELOPER_MODE=false\n", encoding="utf-8")
    monkeypatch.delenv("SOME_REQUIRED_API_KEY", raising=False)

    with pytest.raises(ModuleExecutionError) as excinfo:
        run_module(workspace, "fetch.env_probe", {})

    assert "SOME_REQUIRED_API_KEY" in str(excinfo.value)


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
    assert (workspace / ".env").exists()
    assert not (tmp_path / ".env").exists(), "must not create a second project-level .env"
    out = capsys.readouterr().out
    assert "CENSUS_API_KEY" in out


def test_bundled_env_example_ships_inside_the_package() -> None:
    """The fallback .env.example must live in the package, not at a repo root.

    An installed wheel has no repo root: a `parents[2] / ".env.example"` path
    resolves into site-packages' parent and never exists. The bundled template
    is the only copy guaranteed present in both layouts.
    """
    from sancho.constants import BUNDLED_ENV_EXAMPLE, TEMPLATES_ROOT

    assert BUNDLED_ENV_EXAMPLE.exists()
    assert BUNDLED_ENV_EXAMPLE.is_relative_to(TEMPLATES_ROOT)


def test_env_example_contents_falls_back_to_bundled_template(tmp_path: Path) -> None:
    """A workspace with no .env.example (e.g. created by an older version)
    must still get key sign-up instructions, sourced from the bundled copy."""
    from sancho.constants import BUNDLED_ENV_EXAMPLE
    from sancho.env_keys import _env_example_contents

    path, contents = _env_example_contents(tmp_path)
    assert path == BUNDLED_ENV_EXAMPLE
    assert contents is not None
    assert "API" in contents


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
    assert {
        "python",
        "uv",
        "workspace",
        "ownership",
        "library_register",
        "skills",
        "mcp_config",
        "mcp_launch",
        "ready",
    } <= step_names
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
    assert len(payload["mcp_configs_written"]) == 4
    assert "claude_desktop_config_installed" not in payload


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
    assert "ready" in step_names
    assert payload["ready"]["checks"]["sample_module"]["required"] is False
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



def test_sancho_setup_configures_claude_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr("sancho.client_integrations.platform.system", lambda: "Windows")
    capsys.readouterr()
    rc = main(
        [
            "setup",
            "--path",
            str(tmp_path),
            "--no-network",
            "--client",
            "claude-desktop",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    expected_config = fake_home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    client = next(item for item in payload["clients"] if item["client"] == "claude-desktop")
    assert client["state"] == "restart_required"
    config = json.loads(expected_config.read_text(encoding="utf-8"))
    server = config["mcpServers"]["sancho"]
    assert Path(server["command"]).name.lower().startswith("sancho")
    assert server["args"][:2] == ["mcp", "serve"]
    workspace_index = server["args"].index("--workspace") + 1
    assert Path(server["args"][workspace_index]) == tmp_path / WORKSPACE_DIRNAME
    assert server["args"][-2:] == ["--transport", "stdio"]
    clients_step = next(s for s in payload["steps"] if s["name"] == "clients")
    assert clients_step["status"] == "warn"


def test_claude_desktop_config_uses_appdata_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sancho.mcp.config import claude_desktop_config_path

    roaming = tmp_path / "RoamingProfile"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setattr("sancho.mcp.config._current_platform", lambda: "win32")

    assert claude_desktop_config_path() == roaming / "Claude" / "claude_desktop_config.json"


def test_sancho_setup_install_claude_desktop_is_nonfatal_on_linux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr("sancho.client_integrations.platform.system", lambda: "Linux")
    capsys.readouterr()
    rc = main(
        [
            "setup",
            "--path",
            str(tmp_path),
            "--no-network",
            "--client",
            "claude-desktop",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_failures"] is False
    assert len(payload["mcp_configs_written"]) == 4
    client = next(item for item in payload["clients"] if item["client"] == "claude-desktop")
    assert client["state"] in {"absent", "restart_required"}


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
    assert "uv build --wheel --out-dir" in setup_sh
    assert 'uv tool install --reinstall "$wheel_path"' in setup_sh
    assert 'setup --path "$repo_root" --switch-workspace' in setup_sh
    assert "uv tool uninstall" not in setup_sh
    assert "uv python install 3.11" not in setup_sh
    assert "--python 3.11" not in setup_sh
    assert "--force" not in setup_sh
    assert "uv build --wheel --out-dir" in setup_bat
    assert 'uv tool install --reinstall "%WHEEL_PATH%"' in setup_bat
    assert 'setup --path "%REPO_ROOT%" --switch-workspace' in setup_bat
    assert "uv tool uninstall" not in setup_bat
    assert "uv python install 3.11" not in setup_bat
    assert "--python 3.11" not in setup_bat
    assert "--force" not in setup_bat
    assert "enabledelayedexpansion" not in setup_bat.lower()
    assert "where python" not in setup_bat.lower()
    # cmd.exe parses a complete parenthesized block before executing it, so
    # literal parentheses in an ECHO inside an IF block must be escaped.
    assert "Installing the Python package manager ^(uv^)..." in setup_bat
    assert "EXITCODE=$?" in command
    assert "Press Return to close this window." in command


@pytest.mark.skipif(os.name != "nt", reason="requires the native Windows command parser")
def test_windows_installer_uv_bootstrap_block_parses(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo_root = tmp_path / "repo (parser smoke) & safe"
    installer_dir = repo_root / "installers"
    installer_dir.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname = 'smoke'\n", encoding="utf-8")

    setup_bat = (root / "installers" / "setup.bat").read_text(encoding="utf-8")
    bootstrap = '  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"'
    assert bootstrap in setup_bat, "parser smoke replacement must match the real bootstrap line"
    setup_bat = setup_bat.replace(bootstrap, "  goto :parser_smoke_ok", 1)
    setup_bat += "\n:parser_smoke_ok\npopd\nendlocal\nexit /b 0\n"
    smoke_installer = installer_dir / "setup.bat"
    smoke_installer.write_text(setup_bat, encoding="utf-8")

    env = os.environ.copy()
    where_exe = shutil.which("where.exe")
    assert where_exe is not None
    env["PATH"] = str(Path(where_exe).parent)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "call .\\setup.bat"],
        cwd=installer_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Installing the Python package manager (uv)..." in result.stdout
    assert "was unexpected at this time" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="validated by native macOS/Linux CI")
def test_posix_installers_pass_bash_syntax_check() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            "bash",
            "-n",
            str(root / "installers" / "setup.sh"),
            str(root / "installers" / "Install Sancho.command"),
        ],
        check=True,
    )
