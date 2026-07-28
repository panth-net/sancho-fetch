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

MODULE_ID = "fetch.atus"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_atus_api")
    transform = _load_sibling("transform.py", "sancho_fetch_atus_transform")

    year = payload.get("year") if isinstance(payload.get("year"), int) else None
    series_ids_obj = payload.get("series_ids")
    series_ids = (
        [str(item) for item in series_ids_obj if str(item).strip()]
        if isinstance(series_ids_obj, list)
        else None
    )

    source_url = api.build_source_url(year=year)
    params = {"year": year, "series_ids": series_ids or []}
    family_or_dataset_id = f"atus_{year or 'all'}_{'_'.join(series_ids or ['default'])}"

    # Cache handling
    max_age_seconds = resolve_staleness_seconds(
        payload=payload, runtime=context.runtime, module_id=MODULE_ID,
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload, runtime=context.runtime, module_id=MODULE_ID,
    )
    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective = (
            max_age_seconds
            if max_age_seconds is not None
            else DEFAULT_CACHE_MAX_AGE_SECONDS
        )
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
            source_url=source_url, raw=cached.raw, params=params,
        )

    # Fetch and save
    api_key = context.env.get("BLS_API_KEY", "").strip() or None
    start_year = str(year) if year else "2019"
    end_year = str(year) if year else "2023"
    raw = api.fetch_atus(
        runtime_http=context.runtime.get("http", {}),
        api_key=api_key,
        series_ids=series_ids,
        start_year=start_year,
        end_year=end_year,
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
        source_url=source_url, raw=raw, params=params,
    )
