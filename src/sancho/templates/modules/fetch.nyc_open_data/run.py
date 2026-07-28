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
        module_dir, cache_dir, "catalog.json", module_id="fetch.nyc_open_data"
    )
    if path is None:
        raise RuntimeError(
            "catalog.json is missing for fetch.nyc_open_data (not in module dir or catalog cache). "
            "Run 'sancho add fetch.nyc_open_data' or 'sancho module catalog refresh fetch.nyc_open_data'."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog.json must be an object")
    return payload


def _ensure_path(payload: dict[str, Any]) -> str:
    path_obj = payload.get("path")
    if not isinstance(path_obj, str) or not path_obj.strip():
        raise ValueError("--path is required (e.g. --path /resource/erm2-nwe9.json)")
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
    base_obj = payload.get("base", "nyc_v2")
    if not isinstance(base_obj, str) or not base_obj.strip():
        raise ValueError("payload.base must be a non-empty string")
    return base_obj.strip()


def _ensure_params(payload: dict[str, Any]) -> dict[str, Any]:
    params_obj = payload.get("params", {})
    if not isinstance(params_obj, dict):
        raise ValueError("payload.params must be an object")
    return params_obj


def _ensure_body(payload: dict[str, Any]) -> dict[str, Any]:
    body_obj = payload.get("body", {})
    if body_obj is None:
        return {}
    if not isinstance(body_obj, dict):
        raise ValueError("payload.body must be an object when provided")
    return body_obj


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


def _body_field_spec(family: dict[str, Any]) -> dict[str, Any]:
    spec_obj = family.get("body_fields", {})
    if isinstance(spec_obj, dict):
        return spec_obj
    return {}


def _allow_unknown_query_params(family: dict[str, Any]) -> bool:
    return bool(family.get("allow_unknown_query_params", False))


def _allow_unknown_body_fields(family: dict[str, Any]) -> bool:
    return bool(family.get("allow_unknown_body_fields", False))


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


def _validate_param_types(spec: dict[str, Any], payload: dict[str, Any], *, kind: str) -> None:
    for key, value in payload.items():
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
            raise ValueError(f"{kind} '{key}' must be type {expected}")


def _validate_query_params(family: dict[str, Any], params: dict[str, Any]) -> None:
    spec = _query_param_spec(family)
    if not _allow_unknown_query_params(family):
        unknown = sorted([key for key in params.keys() if key not in spec])
        if unknown:
            raise ValueError(f"Unknown query params for family '{family.get('id', '')}': {', '.join(unknown)}")
    _validate_param_types(spec, params, kind="Param")


def _validate_body_fields(family: dict[str, Any], body: dict[str, Any]) -> None:
    spec = _body_field_spec(family)
    if not _allow_unknown_body_fields(family):
        unknown = sorted([key for key in body.keys() if key not in spec])
        if unknown:
            raise ValueError(f"Unknown body fields for family '{family.get('id', '')}': {', '.join(unknown)}")
    _validate_param_types(spec, body, kind="Body field")


def _find_matching_family(catalog: dict[str, Any], *, base: str, method: str, path: str) -> dict[str, Any]:
    families_obj = catalog.get("families", [])
    if not isinstance(families_obj, list):
        raise ValueError("catalog.json families must be a list")
    for family in families_obj:
        if not isinstance(family, dict):
            continue
        if base not in _family_bases(family):
            continue
        if method not in _family_methods(family):
            continue
        templates = _family_templates(family)
        if any(_path_matches_template(path, template) for template in templates):
            return family
    known = sorted(
        [str(item.get("id", "")) for item in families_obj if isinstance(item, dict) and isinstance(item.get("id"), str)]
    )
    raise ValueError(
        f"No catalog family matched base='{base}', method='{method}', path='{path}'. "
        f"Known family IDs: {', '.join(known)}"
    )


def _resolve_auth_headers(family: dict[str, Any], env: dict[str, str]) -> dict[str, str]:
    import base64
    auth_obj = family.get("auth", {})
    if not isinstance(auth_obj, dict):
        return {}
    required = bool(auth_obj.get("required", False))
    env_id_key = auth_obj.get("env_id", "")
    env_secret_key = auth_obj.get("env_secret", "")
    if isinstance(env_id_key, str) and isinstance(env_secret_key, str) and env_id_key and env_secret_key:
        key_id = str(env.get(env_id_key, "")).strip()
        key_secret = str(env.get(env_secret_key, "")).strip()
        if key_id and key_secret:
            cred = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
            return {"Authorization": f"Basic {cred}"}
        if required:
            raise ValueError(f"Missing required env vars '{env_id_key}' and '{env_secret_key}' for family '{family.get('id', '')}'")
    return {}


def run(*, context: ModuleContext, payload: dict[str, Any]) -> dict[str, Any]:
    client = _load_sibling("client.py", "sancho_fetch_nyc_open_data_client")
    helper = _load_sibling("runtime_helpers.py", "sancho_fetch_nyc_open_data_runtime_helpers")
    catalog = _load_catalog(context.catalog_cache_dir)

    path = _ensure_path(payload)
    method = _ensure_method(payload)
    base = _ensure_base(payload)
    params = _ensure_params(payload)
    body = _ensure_body(payload)

    family = _find_matching_family(catalog, base=base, method=method, path=path)
    params = apply_max_page_size(
        params,
        module_id="fetch.nyc_open_data",
        endpoint=path,
        family=family,
        explicit_keys=params.keys(),
    )
    _validate_query_params(family, params)
    _validate_body_fields(family, body)

    base_url_obj = family.get("base_url")
    base_url = str(base_url_obj) if isinstance(base_url_obj, str) else ""
    response_mode_obj = family.get("response_mode", "json")
    response_mode = str(response_mode_obj).lower() if isinstance(response_mode_obj, str) else "json"
    headers = _resolve_auth_headers(family, context.env)
    dataset_ref = helper.dataset_ref_for_path(path)
    family_id = str(family.get("id", "")).strip()
    family_or_dataset_id = family_id or dataset_ref
    source_url = helper.resolve_source_url(base_url, path)
    cache_params = {"query": params, "body": body}
    max_age_seconds = resolve_staleness_seconds(
        payload=payload,
        runtime=context.runtime,
        module_id="fetch.nyc_open_data",
    )
    cache_enabled = is_raw_cache_enabled(
        payload=payload,
        runtime=context.runtime,
        module_id="fetch.nyc_open_data",
    )

    cached = None
    if max_age_seconds is not None or cache_enabled:
        effective_max_age_seconds = (
            max_age_seconds if max_age_seconds is not None else DEFAULT_CACHE_MAX_AGE_SECONDS
        )
        cached = load_raw(
            data_raw_path=context.data_raw_path,
            module_id="fetch.nyc_open_data",
            family_or_dataset_id=family_or_dataset_id,
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
        return {
            "provider": "nyc_open_data",
            "dataset_ref": dataset_ref,
            "family_id": family.get("id", ""),
            "base": base,
            "method": method,
            "path": path,
            "params": params,
            "body": body,
            "rows": helper.extract_rows(cached.raw),
            "raw": cached.raw,
            "retrieved_at": retrieved_at,
        }

    raw = client.request_direct(
        runtime_http=context.runtime.get("http", {}),
        method=method,
        base_url=base_url,
        path=path,
        params=params,
        json_body=body,
        headers=headers,
        response_mode=response_mode,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    save_raw(
        data_raw_path=context.data_raw_path,
        module_id="fetch.nyc_open_data",
        family_or_dataset_id=family_or_dataset_id,
        raw=raw,
        params=cache_params,
        source_url=source_url,
        fetched_at=fetched_at,
    )

    return {
        "provider": "nyc_open_data",
        "dataset_ref": dataset_ref,
        "family_id": family.get("id", ""),
        "base": base,
        "method": method,
        "path": path,
        "params": params,
        "body": body,
        "rows": helper.extract_rows(raw),
        "raw": raw,
        "retrieved_at": fetched_at,
    }
