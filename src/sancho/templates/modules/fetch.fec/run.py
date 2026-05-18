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
        module_dir, cache_dir, "catalog.json", module_id="fetch.fec"
    )
    if path is None:
        raise RuntimeError(
            "catalog.json is missing for fetch.fec (not in module dir or catalog cache). "
            "Run 'sancho add fetch.fec' or 'sancho module catalog refresh fetch.fec'."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog.json must be an object")
    return payload


def _ensure_path(payload: dict[str, Any]) -> str:
    path_obj = payload.get("path")
    if not isinstance(path_obj, str) or not path_obj.strip():
        raise ValueError("--path is required (e.g. --path /candidates/search/)")
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
    base_obj = payload.get("base", "v1")
    if not isinstance(base_obj, str) or not base_obj.strip():
        raise ValueError("payload.base must be a non-empty string")
    return base_obj.strip()


def _ensure_params(payload: dict[str, Any]) -> dict[str, Any]:
    params_obj = payload.get("params", {})
    if not isinstance(params_obj, dict):
        raise ValueError("payload.params must be an object")
    return params_obj


def _family_list(family: dict[str, Any], key: str) -> list[str]:
    values_obj = family.get(key, [])
    if not isinstance(values_obj, list):
        return []
    values = [str(item) for item in values_obj if isinstance(item, str)]
    if key == "methods":
        return [value.upper() for value in values]
    return values


def _template_to_pattern(template: str) -> str:
    escaped = re.escape(template)
    return "^" + re.sub(r"\\\{[A-Za-z0-9_]+\\\}", r"[^/]+", escaped) + "$"


def _path_matches_template(path: str, template: str) -> bool:
    return re.match(_template_to_pattern(template), path) is not None


def _find_matching_family(catalog: dict[str, Any], *, base: str, method: str, path: str) -> dict[str, Any]:
    families_obj = catalog.get("families", [])
    if not isinstance(families_obj, list):
        raise ValueError("catalog.json families must be a list")
    for family in families_obj:
        if not isinstance(family, dict):
            continue
        if base not in _family_list(family, "base_aliases"):
            continue
        if method not in _family_list(family, "methods"):
            continue
        if any(_path_matches_template(path, template) for template in _family_list(family, "path_templates")):
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
        # OpenFEC documents many query params as arrays, but the API accepts
        # either repeated params or a single scalar value.
        return isinstance(value, (list, str, int, float)) and not isinstance(value, bool)
    if expected == "dict":
        return isinstance(value, dict)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _validate_query_params(family: dict[str, Any], values: dict[str, Any]) -> None:
    family_id = str(family.get("id", ""))
    spec_obj = family.get("query_params", {})
    spec = spec_obj if isinstance(spec_obj, dict) else {}
    if not bool(family.get("allow_unknown_query_params", False)):
        unknown = sorted([key for key in values.keys() if key not in spec])
        if unknown:
            raise ValueError(f"Unknown query params for family '{family_id}': {', '.join(unknown)}")
    required = [key for key, meta in spec.items() if isinstance(key, str) and isinstance(meta, dict) and bool(meta.get("required"))]
    missing = [name for name in required if name not in values]
    if missing:
        raise ValueError(f"Missing required query params for family '{family_id}': {', '.join(missing)}")
    for key, value in values.items():
        meta = spec.get(key, {})
        if not isinstance(meta, dict):
            continue
        expected_obj = meta.get("type")
        if not isinstance(expected_obj, str) or not expected_obj.strip():
            continue
        if not _is_expected_type(value, expected_obj.strip()):
            raise ValueError(f"Param '{key}' must be type {expected_obj.strip()}")


def _resolve_auth_query(family: dict[str, Any], env: dict[str, str]) -> dict[str, str]:
    auth_obj = family.get("auth", {})
    if not isinstance(auth_obj, dict):
        return {}
    query_obj = auth_obj.get("query", {})
    required = bool(auth_obj.get("required", False))
    if not isinstance(query_obj, dict):
        query_obj = {}
    values: dict[str, str] = {}
    missing: list[str] = []
    for query_key, env_key in query_obj.items():
        if not isinstance(query_key, str) or not isinstance(env_key, str):
            continue
        token = str(env.get(env_key, "")).strip()
        if not token:
            missing.append(env_key)
            continue
        values[query_key] = token
    if required and missing:
        raise ValueError(f"Missing required env var(s) for family '{family.get('id', '')}': {', '.join(sorted(set(missing)))}")
    return values


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("results", "items", "data", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return [raw]
    return []


def _usage_notice(path: str) -> dict[str, str] | None:
    if path.startswith("/schedules/schedule_a") or "contributor" in path:
        return {
            "message": (
                "FEC individual contributor information has legal limits around "
                "sale, solicitation, and commercial use."
            ),
            "source": "https://www.fec.gov/updates/sale-or-use-contributor-information/",
        }
    return None


def _resolve_source_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    client = _load_sibling("client.py", "sancho_fetch_fec_client")
    pagination = _load_sibling("pagination.py", "sancho_fetch_fec_pagination")
    catalog = _load_catalog(context.catalog_cache_dir)

    path = _ensure_path(payload)
    method = _ensure_method(payload)
    base = _ensure_base(payload)
    params = _ensure_params(payload)
    explicit_per_page = "per_page" in params
    family = _find_matching_family(catalog, base=base, method=method, path=path)
    family_id = str(family.get("id", "")).strip()
    pagination_config = pagination.normalize_config(payload)

    default_query_obj = family.get("default_query_params", {})
    effective_params = {}
    if "params" not in payload and isinstance(default_query_obj, dict):
        effective_params.update(default_query_obj)
    effective_params.update(params)
    effective_params = pagination.apply_page_size(
        effective_params,
        family=family,
        config=pagination_config,
        explicit_per_page=explicit_per_page,
    )
    _validate_query_params(family, effective_params)

    base_url_obj = family.get("base_url")
    base_url = str(base_url_obj) if isinstance(base_url_obj, str) else ""
    response_mode_obj = family.get("response_mode", "json")
    response_mode = str(response_mode_obj).lower() if isinstance(response_mode_obj, str) else "json"
    auth_query = _resolve_auth_query(family, context.env)

    source_url = _resolve_source_url(base_url, path)
    cache_params = {"query": effective_params, "method": method, "pagination": pagination_config}
    max_age_seconds = resolve_staleness_seconds(payload=payload, runtime=context.runtime, module_id="fetch.fec")
    cache_enabled = is_raw_cache_enabled(payload=payload, runtime=context.runtime, module_id="fetch.fec")

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective_max_age_seconds = max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id="fetch.fec",
            family_or_dataset_id=family_id or (path.strip("/").replace("/", "_") or "default"),
            params=cache_params,
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
        output = {
            "provider": "fec",
            "dataset_ref": "usgov_fec",
            "family_id": family_id,
            "base": base,
            "method": method,
            "path": path,
            "params": effective_params,
            "rows": _extract_rows(cached.raw),
            "raw": cached.raw,
            "pagination": pagination.summarize(cached.raw, params=effective_params, config=pagination_config),
            "retrieved_at": retrieved_at,
        }
        notice = _usage_notice(path)
        if notice is not None:
            output["usage_notice"] = notice
        return output

    raw = pagination.fetch(
        client=client,
        runtime_http=context.runtime.get("http", {}),
        method=method,
        base_url=base_url,
        path=path,
        params=effective_params,
        headers={},
        response_mode=response_mode,
        auth_query=auth_query,
        config=pagination_config,
    )

    fetched_at = datetime.now(timezone.utc).isoformat()
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id="fetch.fec",
        family_or_dataset_id=family_id or (path.strip("/").replace("/", "_") or "default"),
        raw=raw,
        params=cache_params,
        source_url=source_url,
        fetched_at=fetched_at,
    )
    output = {
        "provider": "fec",
        "dataset_ref": "usgov_fec",
        "family_id": family_id,
        "base": base,
        "method": method,
        "path": path,
        "params": effective_params,
        "rows": _extract_rows(raw),
        "raw": raw,
        "pagination": pagination.summarize(raw, params=effective_params, config=pagination_config),
        "retrieved_at": fetched_at,
    }
    notice = _usage_notice(path)
    if notice is not None:
        output["usage_notice"] = notice
    return output
