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


MODULE_ID = "fetch.census.htops"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_census_htops_api")
    transform = _load_sibling(
        "transform.py", "sancho_fetch_census_htops_transform"
    )

    variables_obj = payload.get("variables", [])
    variables = (
        variables_obj if isinstance(variables_obj, list) and variables_obj
        else ["UNITS_TOTAL"]
    )
    time = str(payload.get("time", "2023"))
    geography = str(payload.get("geography", "us:1"))
    week_obj = payload.get("week")
    week = week_obj if isinstance(week_obj, int) else None

    source_url = "https://api.census.gov/data/timeseries/hps"
    family_or_dataset_id = f"hps_{geography.replace(':', '_')}_{time}"
    if week is not None:
        family_or_dataset_id = f"{family_or_dataset_id}_week_{week}"
    params = {
        "variables": variables,
        "time": time,
        "geography": geography,
        "week": week,
    }
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
            geography=geography, time=time, rows=cached.raw,
        )

    rows = api.fetch_htops_rows(
        runtime_http=context.runtime.get("http", {}),
        api_key=context.env.get("CENSUS_API_KEY", ""),
        variables=variables,
        time=time,
        geography=geography,
        week=week,
    )
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=rows,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(
        geography=geography, time=time, rows=rows,
    )
