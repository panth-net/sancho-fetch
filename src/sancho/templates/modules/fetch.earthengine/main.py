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

MODULE_ID = "fetch.earthengine"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_earthengine_api")
    transform = _load_sibling("transform.py", "sancho_fetch_earthengine_transform")

    dataset_id = str(payload.get("dataset_id", ""))
    if not dataset_id:
        raise ValueError("dataset_id is required (e.g. 'MODIS/006/MOD13A2')")

    bbox = payload.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("bbox is required as [west, south, east, north]")

    mode = str(payload.get("mode", "raster")).lower()
    project = context.env.get("EARTHENGINE_PROJECT", "").strip() or None

    params = {
        "dataset_id": dataset_id,
        "bbox": bbox,
        "mode": mode,
    }
    family_or_dataset_id = dataset_id.replace("/", "_")
    source_url = f"earthengine://{dataset_id}"

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
        return transform.build_output(raw=cached.raw, params=params)

    if mode == "vector":
        raw = api.extract_vector_features(
            project=project,
            dataset_id=dataset_id,
            bbox=bbox,
            limit=int(payload.get("limit", 1000)),
            properties=payload.get("properties"),
        )
    else:
        raw = api.extract_raster_stats(
            project=project,
            dataset_id=dataset_id,
            bbox=bbox,
            bands=payload.get("bands"),
            reducer=str(payload.get("reducer", "mean")),
            date_start=payload.get("date_start"),
            date_end=payload.get("date_end"),
            scale=int(payload.get("scale", 1000)),
        )

    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(raw=raw, params=params)
