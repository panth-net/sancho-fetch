"""Fail closed before any immutable Sancho release artifact is published."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("pyproject.toml version is missing")
    return match.group(1)


def _json_version(path: Path, key: str = "version") -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))[key])


def check_versions(tag: str | None) -> str:
    version = _project_version()
    init_match = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        (ROOT / "src" / "sancho" / "__init__.py").read_text(encoding="utf-8"),
    )
    values = {
        "package": version,
        "python": init_match.group(1) if init_match else "missing",
        "mcpb": _json_version(ROOT / "integrations" / "claude-desktop" / "manifest.json"),
        "claude_plugin": _json_version(
            ROOT / "integrations" / "claude-code-plugin" / ".claude-plugin" / "plugin.json"
        ),
        "claude_marketplace": str(
            json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["plugins"][0]["version"]
        ),
        "registry": _json_version(ROOT / "server.json"),
    }
    registry = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"mcp-name: {registry['name']}" not in readme:
        raise RuntimeError("README.md is missing the MCP Registry PyPI ownership marker")
    registry_versions = {
        str(item.get("version"))
        for item in registry.get("packages", [])
        if isinstance(item, dict) and item.get("registryType") == "pypi"
    }
    if registry_versions != {version}:
        raise RuntimeError(f"Registry PyPI package version differs: {registry_versions}")
    runtime = (ROOT / "integrations" / "claude-desktop" / "pyproject.toml").read_text(encoding="utf-8")
    if f'sancho-fetch=={version}' not in runtime:
        raise RuntimeError("MCPB runtime dependency does not exactly match the package version")
    mismatches = {name: value for name, value in values.items() if value != version}
    if mismatches:
        raise RuntimeError(f"release versions differ from {version}: {mismatches}")
    if tag is not None and tag != f"v{version}":
        raise RuntimeError(f"release tag {tag!r} must equal v{version}")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise RuntimeError(f"CHANGELOG.md has no {version} release section")
    return version


def verify_mcpb() -> str:
    bundle_path = ROOT / "integrations" / "claude-desktop" / "sancho.mcpb"
    before = bundle_path.read_bytes() if bundle_path.exists() else None
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_mcpb.py")], check=True)
    after = bundle_path.read_bytes()
    if before != after:
        raise RuntimeError("committed MCPB was stale; rebuild and commit it before tagging")
    with zipfile.ZipFile(bundle_path) as bundle:
        names = bundle.namelist()
        if names != sorted(names):
            raise RuntimeError("MCPB members are not deterministically ordered")
    return hashlib.sha256(after).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Expected immutable Git tag, for example v0.3.0")
    args = parser.parse_args()
    version = check_versions(args.tag)
    digest = verify_mcpb()
    print(json.dumps({"version": version, "tag": args.tag, "mcpb_sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
