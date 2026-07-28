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


MODULE_ID = "fetch.eurostat"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_eurostat_api")
    transform = _load_sibling("transform.py", "sancho_fetch_eurostat_transform")

    dataset_obj = payload.get("dataset")
    dataset = str(dataset_obj).strip() if isinstance(dataset_obj, str) else ""
    if not dataset:
        raise ValueError(
            "payload.dataset is required: an Eurostat dataset code such as "
            "'une_rt_a' (unemployment), 'prc_hicp_manr' (inflation), or "
            "'demo_pjan' (population)."
        )
    filters_obj = payload.get("filters")
    filters = dict(filters_obj) if isinstance(filters_obj, dict) else {}
    lang_obj = payload.get("lang")
    lang = str(lang_obj).strip().upper() if isinstance(lang_obj, str) and str(lang_obj).strip() else "EN"

    source_url = f"{api.BASE_URL}/{dataset}"
    params = {"dataset": dataset, "filters": filters, "lang": lang}

    max_age_seconds = resolve_staleness_seconds(payload=payload, runtime=context.runtime, module_id=MODULE_ID)
    cache_enabled = is_raw_cache_enabled(payload=payload, runtime=context.runtime, module_id=MODULE_ID)

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective = max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id=MODULE_ID,
            family_or_dataset_id=dataset,
            params=params,
            source_url=source_url,
            max_age_seconds=effective,
        )
    if cached is not None:
        return transform.build_output(source_url=source_url, raw=cached.raw, params=params)

    response = api.fetch_dataset(
        runtime_http=context.runtime.get("http", {}),
        dataset=dataset,
        filters=filters,
        lang=lang,
    )
    # Cache the untouched response plus the decoded rows: the response stays
    # faithful, and the rows give the public export a clean table (.xlsx).
    raw = {"response": response, "rows": transform.jsonstat_rows(response)}
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=dataset,
        raw=raw,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(source_url=source_url, raw=raw, params=params)
