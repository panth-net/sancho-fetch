from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.data_store import (
    DEFAULT_CACHE_MAX_AGE_SECONDS,
    is_raw_cache_enabled,
    load_raw,
    resolve_staleness_seconds,
    save_raw,
)


MODULE_ID = "fetch.vdem"
DEFAULT_VERSION = "14"
DEFAULT_INDICATORS = ["v2x_polyarchy", "v2x_libdem", "v2x_partipdem", "v2x_delibdem", "v2x_egaldem"]


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_vdem_api")
    transform = _load_sibling("transform.py", "sancho_fetch_vdem_transform")

    version = str(payload.get("version") or DEFAULT_VERSION)
    indicators_obj = payload.get("indicators") or DEFAULT_INDICATORS
    indicators = [str(x) for x in indicators_obj] if isinstance(indicators_obj, list) else DEFAULT_INDICATORS
    country = payload.get("country")
    country_filter = str(country).upper() if isinstance(country, str) and country.strip() else None
    year_min = payload.get("year_min") if isinstance(payload.get("year_min"), int) else None
    year_max = payload.get("year_max") if isinstance(payload.get("year_max"), int) else None

    source_url = api.build_source_url(version=version)
    params = {
        "version": version,
        "indicators": indicators,
        "country": country_filter,
        "year_min": year_min,
        "year_max": year_max,
    }
    family_or_dataset_id = f"vdem_v{version}"

    max_age_seconds = resolve_staleness_seconds(
        payload=payload,
        runtime=context.runtime,
        module_id=MODULE_ID,
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload,
        runtime=context.runtime,
        module_id=MODULE_ID,
    )

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective = max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id=MODULE_ID,
            family_or_dataset_id=family_or_dataset_id,
            params=params,
            source_url=source_url,
            max_age_seconds=effective,
        )
    if cached is not None:
        return transform.build_output(
            version=version,
            source_url=source_url,
            raw=cached.raw,
            params=params,
        )

    raw = api.fetch_vdem_core(
        runtime_http=context.runtime.get("http", {}),
        archive_cache_dir=Path(context.data_raw_path) / MODULE_ID / "archive",
        version=version,
        indicators=indicators,
        country=country_filter,
        year_min=year_min,
        year_max=year_max,
    )
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(
        version=version,
        source_url=source_url,
        raw=raw,
        params=params,
    )
