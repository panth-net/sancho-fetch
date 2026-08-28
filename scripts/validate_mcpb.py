"""Validate the MCPB against an immutable official v0.4 schema."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "integrations" / "claude-desktop"
SCHEMA_URL = (
    "https://raw.githubusercontent.com/modelcontextprotocol/mcpb/"
    "70fe3b34cd6dff1b3bba046638edc72a6467a4fb/"
    "schemas/mcpb-manifest-v0.4.schema.json"
)
SCHEMA_SHA256 = "068557824c651d6d49b86ad132adeafe62ca788d918b3e1e2b224bf0f91320fd"


def validate() -> None:
    with urllib.request.urlopen(SCHEMA_URL, timeout=20) as response:
        raw_schema = response.read()
    digest = hashlib.sha256(raw_schema).hexdigest()
    if digest != SCHEMA_SHA256:
        raise RuntimeError(f"official MCPB schema digest changed: {digest}")
    schema = json.loads(raw_schema)
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)

    project_version = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    runtime = (BUNDLE_DIR / "pyproject.toml").read_text(encoding="utf-8")
    if not project_version or f'sancho-fetch=={project_version.group(1)}' not in runtime:
        raise RuntimeError("MCPB dependency must exactly match the Sancho package version")
    if manifest["version"] != project_version.group(1):
        raise RuntimeError("MCPB manifest and package versions differ")


if __name__ == "__main__":
    validate()
    print("MCPB manifest and pinned runtime validated")
