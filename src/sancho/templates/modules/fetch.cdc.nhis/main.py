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


MODULE_ID = "fetch.cdc.nhis"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_cdc_nhis_api")
    transform = _load_sibling("transform.py", "sancho_fetch_cdc_nhis_transform")

    year_obj = payload.get("year", 2023)
    year = year_obj if isinstance(year_obj, int) else 2023
    file_kind = str(payload.get("file_kind", "adult"))
    limit_obj = payload.get("limit", 1000)
    limit = limit_obj if isinstance(limit_obj, int) and limit_obj > 0 else 1000

    source_url = api.build_source_url(year=year, file_kind=file_kind)
    family_or_dataset_id = f"nhis_{year}_{file_kind}"
    params = {"year": year, "file_kind": file_kind, "limit": limit}

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

    raw = api.fetch_nhis(
        runtime_http=context.runtime.get("http", {}),
        year=year,
        file_kind=file_kind,
        limit=limit,
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
