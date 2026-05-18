from __future__ import annotations

import json
from pathlib import Path


def test_npm_cli_exposes_single_npx_launcher() -> None:
    package_json = Path("npm-cli/package.json")
    payload = json.loads(package_json.read_text(encoding="utf-8-sig"))
    bins = payload.get("bin", {})
    assert bins == {
        "sancho": "bin/sancho.js",
        "sancho-mcp-quick": "bin/sancho-mcp-quick.js",
    }

    launcher = Path("npm-cli/bin/sancho.js")
    text = launcher.read_text(encoding="utf-8")
    assert '"uvx"' in text
    assert '"--from"' in text
    assert '"sancho-fetch"' in text
    assert '"sancho"' in text
    assert "shell:" not in text
    assert "uvx.exe" in text


def test_npm_mcp_quick_launcher_uses_sancho_package() -> None:
    launcher = Path("npm-cli/bin/sancho-mcp-quick.js")
    text = launcher.read_text(encoding="utf-8")
    assert '"uvx"' in text
    assert '"--from"' in text
    assert '"sancho-fetch"' in text
    assert '"sancho"' in text
    assert "shell:" not in text


def test_npm_package_includes_license_file() -> None:
    payload = json.loads(Path("npm-cli/package.json").read_text(encoding="utf-8-sig"))
    assert payload["license"] == "SEE LICENSE IN LICENSE"
    assert "LICENSE" in payload["files"]
    assert Path("npm-cli/LICENSE").exists()
