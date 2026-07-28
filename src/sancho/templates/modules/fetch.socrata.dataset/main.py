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
from sancho.runtime.page_size import SOCRATA_MAX_LIMIT


MODULE_ID = "fetch.socrata.dataset"


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    api = _load_sibling("api.py", "sancho_fetch_socrata_api")
    transform = _load_sibling("transform.py", "sancho_fetch_socrata_transform")

    domain = str(payload.get("domain", "data.seattle.gov"))
    dataset_id = str(payload.get("dataset_id", "kzjm-xkqj"))
    limit = int(payload.get("limit", SOCRATA_MAX_LIMIT))
    where = str(payload.get("where", ""))
    extra_params_obj = payload.get("params", {})
    extra_params = extra_params_obj if isinstance(extra_params_obj, dict) else {}

    domain_for_url = domain.strip()
    if domain_for_url.startswith("https://"):
        domain_for_url = domain_for_url[len("https://") :]
    if domain_for_url.startswith("http://"):
        domain_for_url = domain_for_url[len("http://") :]
    domain_for_url = domain_for_url.strip("/")
    source_url = f"https://{domain_for_url}/resource/{dataset_id}.json"
    family_or_dataset_id = dataset_id
    params = {
        "limit": limit,
        "where": where,
        "extra": extra_params,
    }
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
            params=params,
            source_url=source_url,
            max_age_seconds=effective_max_age_seconds,
        )
    if cached is not None:
        return transform.build_output(domain=domain, dataset_id=dataset_id, raw=cached.raw)

    raw = api.fetch_socrata_dataset(
        runtime_http=context.runtime.get("http", {}),
        app_token="",
        domain=domain,
        dataset_id=dataset_id,
        limit=limit,
        where=where,
        extra_params=extra_params,
        env=context.env,
    )
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id=MODULE_ID,
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=params,
        source_url=source_url,
    )
    return transform.build_output(domain=domain, dataset_id=dataset_id, raw=raw)
