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


MODULE_ID = "fetch.census.decennial"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_census_decennial_api")
    transform = _load_sibling(
        "transform.py", "sancho_fetch_census_decennial_transform"
    )

    geography = payload.get("geography")
    in_geography_obj = payload.get("in_geography")
    in_geography = (
        in_geography_obj.strip()
        if isinstance(in_geography_obj, str) and in_geography_obj.strip()
        else None
    )
    year = str(payload.get("year", "2020"))
    dataset = str(payload.get("dataset", "dhc"))
    variables_obj = payload.get("variables", ["NAME", "P1_001N"])
    variables = (
        variables_obj if isinstance(variables_obj, list) else ["NAME", "P1_001N"]
    )

    source_url = f"https://api.census.gov/data/{year}/dec/{dataset}"
    family_or_dataset_id = (
        geography.strip()
        if isinstance(geography, str) and geography.strip()
        else "default"
    )
    if in_geography:
        family_or_dataset_id = (
            f"{family_or_dataset_id}__in__{in_geography.replace(':', '_')}"
        )
    params = {
        "geography": geography,
        "in_geography": in_geography,
        "year": year,
        "dataset": dataset,
        "variables": variables,
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
            geography=geography, year=year, dataset=dataset, rows=cached.raw,
        )

    rows = api.fetch_decennial_rows(
        runtime_http=context.runtime.get("http", {}),
        api_key=context.env.get("CENSUS_API_KEY", ""),
        year=year,
        dataset=dataset,
        geography=geography,
        variables=variables,
        in_geography=in_geography,
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
        geography=geography, year=year, dataset=dataset, rows=rows,
    )
