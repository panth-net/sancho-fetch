from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from scripts.generate_privacy_inventory import generate
from scripts.publish_registry_idempotent import _contains
from sancho import __version__ as SANCHO_VERSION
from sancho.mcp.config import generate_client_config
from sancho.workspace import initialize_workspace

pytestmark = pytest.mark.release_gate

ROOT = Path(__file__).resolve().parents[1]


def test_claude_plugin_has_explicit_existing_cli_contract() -> None:
    plugin_root = ROOT / "integrations" / "claude-code-plugin"
    manifest = json.loads(
        (plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "sancho-fetch"
    assert manifest["version"] == SANCHO_VERSION
    mcp = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["sancho"] == {
        "command": "sancho",
        "args": ["mcp", "serve", "--transport", "stdio"],
    }
    readme = (plugin_root / "README.md").read_text(encoding="utf-8")
    assert f"sancho-fetch=={SANCHO_VERSION}" in readme
    assert "existing Sancho" in readme
    assert (plugin_root / "skills" / "sancho" / "SKILL.md").exists()
    assert (plugin_root / "skills" / "sancho-update" / "SKILL.md").exists()


def test_cursor_fallback_is_reversible_current_deeplink(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path, "sancho-workspace", "operator")
    payload = generate_client_config("cursor", workspace)
    fallback = payload["install_fallback"]
    assert fallback["state"] == "user_action_required"
    parsed = urlparse(fallback["url"])
    assert parsed.scheme == "cursor"
    assert parsed.netloc == "anysphere.cursor-deeplink"
    assert parsed.path == "/mcp/install"
    query = parse_qs(parsed.query)
    assert query["name"] == ["sancho"]
    decoded = json.loads(base64.b64decode(query["config"][0]))
    assert decoded == payload["mcpServers"]["sancho"]
    assert decoded["type"] == "stdio"


def test_pypi_readme_proves_registry_namespace_ownership() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    registry = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert f"mcp-name: {registry['name']}" in readme


def test_committed_privacy_inventory_is_current_and_describes_auth_flows() -> None:
    committed = json.loads(
        (ROOT / "docs" / "privacy" / "upstream-inventory.json").read_text(encoding="utf-8")
    )
    assert committed == generate()
    assert committed["module_count"] >= 120
    assert committed["unique_upstream_domain_count"] >= 100
    credentialed = [item for item in committed["modules"] if item["credential_environment_variables"]]
    assert credentialed
    assert all(item["authentication_methods"] != ["none-declared"] for item in credentialed)
    assert all(item["credential_destination"] for item in credentialed)


def test_registry_retry_accepts_only_an_identical_public_subset() -> None:
    expected = {"name": "example/server", "packages": [{"identifier": "example", "version": "1"}]}
    actual = {
        "name": "example/server",
        "packages": [{"identifier": "example", "version": "1", "extra": "registry"}],
        "_meta": {"status": "active"},
    }
    assert _contains(actual, expected)
    changed = copy.deepcopy(actual)
    changed["packages"][0]["version"] = "2"
    assert not _contains(changed, expected)
