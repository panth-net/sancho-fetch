from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
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
from sancho.runtime.page_size import apply_max_page_size


def _load_sibling(file_name: str, logical_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(logical_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import sibling module: {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_catalog(cache_dir: Path | None) -> dict[str, Any]:
    from sancho.catalog_cache import resolve_catalog_artifact

    module_dir = Path(__file__).parent
    path = resolve_catalog_artifact(
        module_dir, cache_dir, "catalog.json", module_id="fetch.world_bank"
    )
    if path is None:
        raise RuntimeError(
            "catalog.json is missing for fetch.world_bank (not in module dir or catalog cache). "
            "Run 'sancho add fetch.world_bank' or 'sancho module catalog refresh fetch.world_bank'."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog.json must be an object")
    return payload


def _ensure_path(payload: dict[str, Any]) -> str:
    path_obj = payload.get("path")
    if not isinstance(path_obj, str) or not path_obj.strip():
        raise ValueError("--path is required (e.g. --path /country/all/indicator/SP.POP.TOTL)")
    path = path_obj.strip()
    if path.startswith("//"):
        path = path[1:]
    elif not path.startswith("/"):
        path = "/" + path
    return path


def _ensure_method(payload: dict[str, Any]) -> str:
    method_obj = payload.get("method", "GET")
    if not isinstance(method_obj, str) or not method_obj.strip():
        raise ValueError("payload.method must be a non-empty string")
    return method_obj.strip().upper()


def _ensure_base(payload: dict[str, Any]) -> str:
    base_obj = payload.get("base", "v2")
    if not isinstance(base_obj, str) or not base_obj.strip():
        raise ValueError("payload.base must be a non-empty string")
    return base_obj.strip()


def _ensure_params(payload: dict[str, Any]) -> dict[str, Any]:
    params_obj = payload.get("params", {})
    if not isinstance(params_obj, dict):
        raise ValueError("payload.params must be an object")
    return params_obj


def _family_methods(family: dict[str, Any]) -> list[str]:
    methods_obj = family.get("methods", [])
    if not isinstance(methods_obj, list):
        return []
    return [str(item).upper() for item in methods_obj if isinstance(item, str)]


def _family_templates(family: dict[str, Any]) -> list[str]:
    templates_obj = family.get("path_templates", [])
    if not isinstance(templates_obj, list):
        return []
    return [str(item) for item in templates_obj if isinstance(item, str)]


def _family_bases(family: dict[str, Any]) -> list[str]:
    bases_obj = family.get("base_aliases", [])
    if not isinstance(bases_obj, list):
        return []
    return [str(item) for item in bases_obj if isinstance(item, str)]


def _template_to_pattern(template: str) -> str:
    escaped = re.escape(template)
    return "^" + re.sub(r"\\\{[A-Za-z0-9_]+\\\}", r"[^/]+", escaped) + "$"


def _path_matches_template(path: str, template: str) -> bool:
    pattern = _template_to_pattern(template)
    return re.match(pattern, path) is not None


def _query_param_spec(family: dict[str, Any]) -> dict[str, Any]:
    spec_obj = family.get("query_params", {})
    if isinstance(spec_obj, dict):
        return spec_obj
    return {}


def _allowed_query_params(family: dict[str, Any]) -> set[str]:
    return set(_query_param_spec(family).keys())


def _allow_unknown_query_params(family: dict[str, Any]) -> bool:
    value = family.get("allow_unknown_query_params", False)
    return bool(value)


def _validate_query_param_names(family: dict[str, Any], params: dict[str, Any]) -> None:
    if _allow_unknown_query_params(family):
        return
    allowed = _allowed_query_params(family)
    unknown = sorted([key for key in params.keys() if key not in allowed])
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"Unknown query params for family '{family.get('id', '')}': {joined}")


def _is_expected_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "float":
        return isinstance(value, float)
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "list":
        return isinstance(value, list)
    if expected == "dict":
        return isinstance(value, dict)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _validate_query_param_types(family: dict[str, Any], params: dict[str, Any]) -> None:
    spec = _query_param_spec(family)
    for key, value in params.items():
        item = spec.get(key, {})
        if not isinstance(item, dict):
            continue
        expected_obj = item.get("type")
        if not isinstance(expected_obj, str):
            continue
        expected = expected_obj.strip()
        if not expected:
            continue
        if not _is_expected_type(value, expected):
            raise ValueError(f"Param '{key}' must be type {expected}")


def _find_matching_family(catalog: dict[str, Any], *, base: str, method: str, path: str) -> dict[str, Any]:
    families_obj = catalog.get("families", [])
    if not isinstance(families_obj, list):
        raise ValueError("catalog.json families must be a list")
    for family in families_obj:
        if not isinstance(family, dict):
            continue
        bases = _family_bases(family)
        methods = _family_methods(family)
        if base not in bases:
            continue
        if method not in methods:
            continue
        templates = _family_templates(family)
        if any(_path_matches_template(path, template) for template in templates):
            return family
    known = sorted(
        [
            str(item.get("id", ""))
            for item in families_obj
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
    )
    raise ValueError(
        f"No catalog family matched base='{base}', method='{method}', path='{path}'. "
        f"Known family IDs: {', '.join(known)}"
    )


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        rows_obj = raw.get("rows")
        if isinstance(rows_obj, list):
            return rows_obj
        for key in ("results", "result", "items", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        projects_obj = raw.get("projects")
        if isinstance(projects_obj, dict):
            return list(projects_obj.values())
        return [raw]
    if isinstance(raw, list):
        if len(raw) >= 2 and isinstance(raw[1], list):
            return raw[1]
        return raw
    return []


def _resolve_source_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _family_or_dataset_id(family: dict[str, Any], path: str) -> str:
    family_id_obj = family.get("id")
    if isinstance(family_id_obj, str) and family_id_obj.strip():
        return family_id_obj.strip()
    normalized = path.strip("/").replace("/", "_")
    return normalized or "default"


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    client = _load_sibling("client.py", "sancho_fetch_world_bank_client")
    catalog = _load_catalog(context.catalog_cache_dir)

    path = _ensure_path(payload)
    method = _ensure_method(payload)
    base = _ensure_base(payload)
    params = _ensure_params(payload)

    family = _find_matching_family(catalog, base=base, method=method, path=path)
    params = apply_max_page_size(
        params,
        module_id="fetch.world_bank",
        endpoint=path,
        family=family,
        base=base,
        explicit_keys=params.keys(),
    )
    _validate_query_param_names(family, params)
    _validate_query_param_types(family, params)

    base_url_obj = family.get("base_url")
    base_url = str(base_url_obj) if isinstance(base_url_obj, str) else ""
    response_mode_obj = family.get("response_mode", "json")
    response_mode = str(response_mode_obj).lower() if isinstance(response_mode_obj, str) else "json"
    headers: dict[str, str] = {}
    family_or_dataset_id = _family_or_dataset_id(family, path)
    source_url = _resolve_source_url(base_url, path)
    max_age_seconds = resolve_staleness_seconds(
        payload=payload,
        runtime=context.runtime,
        module_id="fetch.world_bank",
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload,
        runtime=context.runtime,
        module_id="fetch.world_bank",
    )

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective_max_age_seconds = (
            max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        )
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id="fetch.world_bank",
            family_or_dataset_id=family_or_dataset_id,
            params=params,
            source_url=source_url,
            max_age_seconds=effective_max_age_seconds,
        )
    if cached is not None:
        cached_retrieved_at = cached.metadata.get("fetched_at")
        retrieved_at = (
            str(cached_retrieved_at)
            if isinstance(cached_retrieved_at, str) and cached_retrieved_at.strip()
            else datetime.now(timezone.utc).isoformat()
        )
        rows = _extract_rows(cached.raw)
        return {
            "provider": "world_bank",
            "dataset_ref": "worldbank_wdi_api",
            "family_id": family.get("id", ""),
            "base": base,
            "method": method,
            "path": path,
            "params": params,
            "rows": rows,
            "raw": cached.raw,
            "retrieved_at": retrieved_at,
        }

    raw = client.request_direct(
        runtime_http=context.runtime.get("http", {}),
        method=method,
        base_url=base_url,
        path=path,
        params=params,
        headers=headers,
        response_mode=response_mode,
    )

    fetched_at = datetime.now(timezone.utc).isoformat()
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id="fetch.world_bank",
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=params,
        source_url=source_url,
        fetched_at=fetched_at,
    )
    rows = _extract_rows(raw)
    return {
        "provider": "world_bank",
        "dataset_ref": "worldbank_wdi_api",
        "family_id": family.get("id", ""),
        "base": base,
        "method": method,
        "path": path,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": fetched_at,
    }
