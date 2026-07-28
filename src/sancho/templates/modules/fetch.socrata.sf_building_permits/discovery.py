"""Live catalog discovery for data.sfgov.org. Uses the shared Socrata helper."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from sancho.runtime.socrata_catalog import discover_socrata


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_sf_permits_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    return discover_socrata(
        module_dir=module_dir,
        provider_id=str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.socrata.sf_building_permits")),
        domain=str(getattr(BLUEPRINT, "DOMAIN", "data.sfgov.org")),
        offline=offline,
        schema_version=str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0")),
    )
