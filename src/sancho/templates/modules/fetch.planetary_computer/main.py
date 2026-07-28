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

MODULE_ID = "fetch.planetary_computer"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_planetary_computer_api")
    transform = _load_sibling("transform.py", "sancho_fetch_planetary_computer_transform")

    collection = payload.get("collection")
    mode = str(payload.get("mode", "search" if collection else "list")).lower()
    subscription_key = context.env.get("PC_SDK_SUBSCRIPTION_KEY", "").strip() or None
    limit = int(payload.get("limit", 1000))

    params: dict[str, Any] = {"mode": mode, "collection": collection, "limit": limit}
    family_or_dataset_id = collection or "catalog"
    source_url = f"planetary_computer://{family_or_dataset_id}"

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

    if mode == "list":
        raw = api.list_collections(
            runtime_http=context.runtime.get("http", {}),
            subscription_key=subscription_key,
            limit=limit,
        )
    else:
        if not collection:
            raise ValueError("collection is required for search mode")
        raw = api.search_items(
            runtime_http=context.runtime.get("http", {}),
            subscription_key=subscription_key,
            collection=collection,
            bbox=payload.get("bbox"),
            datetime_range=payload.get("datetime"),
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
    return transform.build_output(raw=raw, params=params)
