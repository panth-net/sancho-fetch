"""Release manifest: what versions ship with the installed Sancho package.

The manifest is generated from the built-in template registry. Each release
of the ``sancho`` Python package ships a fresh set of templates, so the
template registry IS the source of truth for "available versions" without
needing a server.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.modules import load_template_registry, normalize_rel

WORKSPACE_SCHEMA_VERSION = 2  # bumped at Phase 1 when fetched-data replaced data/raw
RELEASE_MANIFEST_FILENAME = "sancho-release-manifest.json"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _template_sha(template_dir: Path) -> str:
    """Hash of all files in the template, sorted, for stability."""
    h = hashlib.sha256()
    for path in sorted(p for p in template_dir.rglob("*") if p.is_file()):
        rel = normalize_rel(path.relative_to(template_dir))
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(_file_sha256(path).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def generate_release_manifest() -> dict[str, Any]:
    registry = load_template_registry()
    modules: dict[str, Any] = {}
    for module_id, template in sorted(registry.items()):
        modules[module_id] = {
            "version": template.version,
            "type": template.type,
            "sha": _template_sha(template.template_dir),
            "paths": [
                normalize_rel(path.relative_to(template.template_dir))
                for path in sorted(p for p in template.template_dir.rglob("*") if p.is_file())
            ],
        }
    return {
        "sancho_version": SANCHO_VERSION,
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "modules": modules,
    }


def write_release_manifest(target: Path) -> Path:
    payload = generate_release_manifest()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return target
