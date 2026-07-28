"""Live catalog discovery for OECD SDMX. Uses the shared SDMX helper."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from sancho.runtime.sdmx_catalog import discover_sdmx


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_oecd_sdmx_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    return discover_sdmx(
        module_dir=module_dir,
        provider_id=str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.oecd_sdmx")),
        base_url=str(getattr(BLUEPRINT, "BASE_URL", "https://sdmx.oecd.org/public/rest")),
        dataflow_path=str(getattr(BLUEPRINT, "DATAFLOW_PATH", "/dataflow/all/all")),
        docs_url=str(getattr(BLUEPRINT, "DOCS_URL", "")),
        offline=offline,
        schema_version=str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0")),
    )
