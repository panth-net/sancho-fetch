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
from sancho.runtime.page_size import apply_max_page_size


MODULE_ID = "fetch.nrel.alt_fuel_stations"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_nrel_alt_fuel_stations_api")
    transform = _load_sibling("transform.py", "sancho_fetch_nrel_alt_fuel_stations_transform")

    # Use /v1.json (list endpoint). /v1/all.json and /v1/nearby.json are interpreted
    # as single-station lookups by ID and return 422.
    endpoint = str(payload.get("endpoint", "https://developer.nrel.gov/api/alt-fuel-stations/v1.json"))
    params_obj = payload.get("params", {})
    caller_param_keys = params_obj.keys() if isinstance(params_obj, dict) else ()
    params = params_obj if isinstance(params_obj, dict) else {}
    params = apply_max_page_size(
        params,
        module_id=MODULE_ID,
        endpoint=endpoint,
        explicit_keys=caller_param_keys,
    )

    family_or_dataset_id = endpoint
    source_url = endpoint
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
        effective_max_age_seconds = (
            max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        )
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id=MODULE_ID,
            family_or_dataset_id=family_or_dataset_id,
            params=params,
            source_url=source_url,
            max_age_seconds=effective_max_age_seconds,
        )
    if cached is not None:
        return transform.build_output(
            endpoint=endpoint,
            raw=cached.raw,
            params=params,
        )

    raw = api.fetch_dataset(
        runtime_http=context.runtime.get("http", {}),
        env=context.env,
        endpoint=endpoint,
        params=params,
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
        endpoint=endpoint,
        raw=raw,
        params=params,
    )
