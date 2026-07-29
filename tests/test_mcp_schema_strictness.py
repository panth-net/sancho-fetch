"""Gate: every shipped module input_schema is valid JSON Schema 2020-12.

The 2026-07-28 MCP spec allows any JSON Schema 2020-12 keywords in tool
inputSchema and subjects them to strict validation — clients may reject
schemas a loose validator used to let slide. Module manifests are passed
verbatim into tools/list, so every shipped manifest must survive a strict
2020-12 metaschema check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

jsonschema = pytest.importorskip("jsonschema", reason="dev extra: pip install jsonschema")

pytestmark = pytest.mark.mcp

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "src" / "sancho" / "templates" / "modules"


def _module_manifests() -> list[tuple[str, dict]]:
    manifests = []
    for child in sorted(TEMPLATE_ROOT.iterdir()):
        manifest_path = child / "module.yaml"
        if child.is_dir() and manifest_path.exists():
            manifests.append((child.name, yaml.safe_load(manifest_path.read_text(encoding="utf-8"))))
    assert manifests, "no module templates found"
    return manifests


@pytest.mark.parametrize("module_id,manifest", _module_manifests(), ids=lambda v: v if isinstance(v, str) else "")
def test_input_schema_is_valid_json_schema_2020_12(module_id: str, manifest: dict) -> None:
    schema = manifest.get("input_schema", {"type": "object"})
    validator = jsonschema.validators.validator_for(
        {"$schema": "https://json-schema.org/draft/2020-12/schema"}
    )
    validator.check_schema(schema)
    # tools/list requires an object schema at the top level.
    assert schema.get("type") == "object", f"{module_id}: inputSchema must be type object"
