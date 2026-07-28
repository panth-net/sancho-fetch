"""Live catalog discovery for data.cms.gov (DCAT /data.json)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from sancho.runtime.dcat_catalog import discover_dcat


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_cms_data_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    return discover_dcat(
        module_dir=module_dir,
        provider_id=str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.cms.data")),
        base_url=str(getattr(BLUEPRINT, "BASE_URL", "https://data.cms.gov")),
        docs_url=str(getattr(BLUEPRINT, "DOCS_URL", "")),
        offline=offline,
        schema_version=str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0")),
    )
