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


MODULE_ID = "fetch.owid_charts"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_owid_charts_api")
    transform = _load_sibling("transform.py", "sancho_fetch_owid_charts_transform")

    slug_raw = payload.get("slug")
    slug = str(slug_raw).strip() if isinstance(slug_raw, str) and slug_raw.strip() else None
    search_raw = payload.get("search")
    search = str(search_raw).strip() if isinstance(search_raw, str) and search_raw.strip() else None
    limit = int(payload.get("limit", 5))

    source_url = f"https://ourworldindata.org/grapher/{slug}" if slug else "https://ourworldindata.org"
    params = {"slug": slug, "search": search, "limit": limit}
    family_or_dataset_id = slug or search or "owid_charts"

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

    raw = api.fetch_owid_charts(
        runtime_http=context.runtime.get("http", {}),
        slug=slug,
        search=search,
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
    return transform.build_output(source_url=source_url, raw=raw, params=params)
