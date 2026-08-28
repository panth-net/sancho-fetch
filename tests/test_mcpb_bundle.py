"""Guards for the committed Claude Desktop bundle and version consistency."""

from __future__ import annotations

import json
import importlib.util
import re
import zipfile
from pathlib import Path

from sancho import __version__ as SANCHO_VERSION

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "integrations" / "claude-desktop"


def test_versions_are_in_sync() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match, "pyproject.toml has no version"
    assert match.group(1) == SANCHO_VERSION, "pyproject.toml and sancho.__version__ differ"
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == SANCHO_VERSION, (
        "integrations/claude-desktop/manifest.json version drifted; "
        "update it and re-run scripts/build_mcpb.py"
    )


def test_manifest_declares_managed_uv_runtime_and_external_workspace() -> None:
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.4"
    assert manifest["server"]["type"] == "uv"
    assert manifest["server"]["entry_point"] == "src/server.py"
    assert manifest["server"]["mcp_config"] == {
        "command": "uv",
        "args": ["run", "--directory", "${__dirname}", "src/server.py"],
        "env": {"SANCHO_MCPB_WORKSPACE": "${user_config.workspace}"},
    }
    assert manifest["user_config"]["workspace"]["type"] == "directory"
    assert manifest["privacy_policies"]

    runtime_project = (BUNDLE_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"sancho-fetch=={SANCHO_VERSION}"' in runtime_project


def test_committed_mcpb_matches_sources() -> None:
    bundle_path = BUNDLE_DIR / "sancho.mcpb"
    assert bundle_path.exists(), "run scripts/build_mcpb.py"
    with zipfile.ZipFile(bundle_path) as bundle:
        assert sorted(bundle.namelist()) == [
            ".mcpbignore",
            "manifest.json",
            "pyproject.toml",
            "src/server.py",
        ]
        for member in bundle.namelist():
            assert bundle.read(member) == (BUNDLE_DIR / member).read_bytes(), (
                f"{member} in sancho.mcpb is stale; re-run scripts/build_mcpb.py"
            )


def test_mcpb_clean_bootstrap_uses_external_workspace_and_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    server_path = BUNDLE_DIR / "src" / "server.py"
    spec = importlib.util.spec_from_file_location("sancho_mcpb_server_test", server_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    external = tmp_path / "External Data & Unicode Ω"
    monkeypatch.setenv("SANCHO_MCPB_WORKSPACE", str(external))
    first = module.bootstrap_workspace()
    first_identity = json.loads((first / ".sancho-workspace.json").read_text(encoding="utf-8"))
    second = module.bootstrap_workspace()
    second_identity = json.loads((second / ".sancho-workspace.json").read_text(encoding="utf-8"))
    assert first == external / "sancho-workspace"
    assert second == first
    assert first_identity["workspace_id"] == second_identity["workspace_id"]
    assert (first / "source" / "fetch" / "fetch_world_bank").exists()
    # The bootstrap lock must live in Sancho's control directory, never inside
    # the data-bearing workspace.
    assert not list(first.rglob("*.lock")), "lock files leaked into the workspace"
