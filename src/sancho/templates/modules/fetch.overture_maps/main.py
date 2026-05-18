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


MODULE_ID = "fetch.overture_maps"

VALID_THEMES = {"addresses", "buildings", "places", "transportation", "base", "divisions"}


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_overture_maps_api")
    transform = _load_sibling("transform.py", "sancho_fetch_overture_maps_transform")

    # --- Extract and validate bbox (REQUIRED) ---
    bbox = payload.get("bbox")
    if bbox is None:
        raise ValueError("bbox is required. Provide [min_lon, min_lat, max_lon, max_lat].")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("bbox must be a list of 4 numbers: [min_lon, min_lat, max_lon, max_lat].")
    try:
        bbox = [float(v) for v in bbox]
    except (TypeError, ValueError):
        raise ValueError("All bbox values must be numbers: [min_lon, min_lat, max_lon, max_lat].")

    theme = str(payload.get("theme", "places"))
    if theme not in VALID_THEMES:
        raise ValueError(
            f"Invalid theme '{theme}'. Must be one of: {', '.join(sorted(VALID_THEMES))}"
        )
    release = str(payload.get("release", "2024-12-18.0"))
    limit = int(payload.get("limit", 1000))

    # Build a stable identifier for caching
    family_or_dataset_id = f"overture_{theme}_{release}"
    source_url = api.build_source_url(release=release, theme=theme)

    max_age_seconds = resolve_staleness_seconds(
        payload=payload,
        runtime=context.runtime,
        module_id=MODULE_ID,
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload,
        runtime=context.runtime,
        module_id=MODULE_ID,
    )

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective_max_age_seconds = (
            max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        )
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id=MODULE_ID,
            family_or_dataset_id=family_or_dataset_id,
            params={"bbox": bbox, "theme": theme, "limit": limit},
            source_url=source_url,
            max_age_seconds=effective_max_age_seconds,
        )
    if cached is not None:
        return transform.build_output(
            source_url=source_url,
            raw=cached.raw,
            theme=theme,
            release=release,
            bbox=bbox,
        )

    raw = api.fetch_overture(
        runtime_http=context.runtime.get("http", {}),
        bbox=bbox,
        theme=theme,
        release=release,
        limit=limit,
    )
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params={"bbox": bbox, "theme": theme, "limit": limit},
        source_url=source_url,
    )
    return transform.build_output(
        source_url=source_url,
        raw=raw,
        theme=theme,
        release=release,
        bbox=bbox,
    )
