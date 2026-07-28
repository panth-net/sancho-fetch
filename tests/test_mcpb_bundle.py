"""Guards for the committed Claude Desktop bundle and version consistency."""

from __future__ import annotations

import json
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


def test_manifest_declares_a_zero_config_node_server() -> None:
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["server"]["type"] == "node"
    assert manifest["server"]["entry_point"] == "server/index.js"
    assert "user_config" not in manifest, "the bundle must stay zero-config"


def test_committed_mcpb_matches_sources() -> None:
    bundle_path = BUNDLE_DIR / "sancho.mcpb"
    assert bundle_path.exists(), "run scripts/build_mcpb.py"
    with zipfile.ZipFile(bundle_path) as bundle:
        assert sorted(bundle.namelist()) == ["manifest.json", "server/index.js"]
        for member in bundle.namelist():
            assert bundle.read(member) == (BUNDLE_DIR / member).read_bytes(), (
                f"{member} in sancho.mcpb is stale; re-run scripts/build_mcpb.py"
            )
