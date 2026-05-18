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


MODULE_ID = "fetch.nd_gain"
VALID_METRICS = {"gain", "vulnerability", "readiness"}


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_nd_gain_api")
    transform = _load_sibling("transform.py", "sancho_fetch_nd_gain_transform")

    country = payload.get("country")
    country_filter = str(country).upper() if isinstance(country, str) and country.strip() else None
    metric = payload.get("metric")
    metric_filter = str(metric).lower() if isinstance(metric, str) and metric.strip() else None
    if metric_filter and metric_filter not in VALID_METRICS:
        metric_filter = None

    source_url = api.DOWNLOAD_PAGE_URL
    params = {"country": country_filter, "metric": metric_filter}
    family_or_dataset_id = "nd_gain_index"

    max_age_seconds = resolve_staleness_seconds(
        payload=payload, runtime=context.runtime, module_id=MODULE_ID,
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload, runtime=context.runtime, module_id=MODULE_ID,
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
            source_url=source_url, raw=cached.raw, params=params,
        )

    raw = api.fetch_nd_gain(
        runtime_http=context.runtime.get("http", {}),
        archive_cache_dir=Path(context.data_raw_path) / MODULE_ID / "archive",
        country=country_filter,
        metric=metric_filter,
    )
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(source_url=source_url, raw=raw, params=params)
