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


MODULE_ID = "fetch.wgi"
ALL_INDICATORS = ["GOV_WGI_VA.EST", "GOV_WGI_PV.EST", "GOV_WGI_GE.EST", "GOV_WGI_RQ.EST", "GOV_WGI_RL.EST", "GOV_WGI_CC.EST"]


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_wgi_api")
    transform = _load_sibling("transform.py", "sancho_fetch_wgi_transform")

    indicators_obj = payload.get("indicators") or ALL_INDICATORS
    indicators = [str(x) for x in indicators_obj] if isinstance(indicators_obj, list) else ALL_INDICATORS
    country = payload.get("country")
    country_filter = str(country).upper() if isinstance(country, str) and country.strip() else None
    year_min = payload.get("year_min") if isinstance(payload.get("year_min"), int) else None
    year_max = payload.get("year_max") if isinstance(payload.get("year_max"), int) else None

    source_url = "https://api.worldbank.org/v2/country/all/indicator/"
    params = {"indicators": indicators, "country": country_filter, "year_min": year_min, "year_max": year_max}
    family_or_dataset_id = "wgi_indicators"

    max_age_seconds = resolve_staleness_seconds(payload=payload, runtime=context.runtime, module_id=MODULE_ID)
    cache_enabled = is_raw_cache_enabled(payload=payload, runtime=context.runtime, module_id=MODULE_ID)

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
        return transform.build_output(source_url=source_url, raw=cached.raw, params=params)

    raw = api.fetch_wgi(
        runtime_http=context.runtime.get("http", {}),
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
    return transform.build_output(source_url=source_url, raw=raw, params=params)
