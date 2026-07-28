from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sancho.cli_hints import ZERO_KEY_PROVIDERS, supported_providers
from sancho.cli_public_export import (
    auto_public_export as _auto_public_export,
    print_primary as _print_primary,
    row_count as _row_count,
)
from sancho.path_utils import safe_slug
from sancho.provider_kits import provider_to_module_id, resolve_provider_catalog
from sancho.templates.runtime.cache_index import iter_cache_records
from sancho.workspace import find_workspace_root


def _resolve_workspace_arg(path_arg: str) -> Path:
    return find_workspace_root(Path(path_arg).resolve())


def _load_params_json(raw: str | None) -> dict:
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--params JSON must be an object")
    return payload


def _load_body_json(raw: str | None) -> dict:
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--body JSON must be an object")
    return payload


def cmd_fetch_catalog(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    module_id, module_dir, catalog = resolve_provider_catalog(workspace_root, args.provider)
    provider_name = str(catalog["provider"])
    families = list(catalog.get("families", []))

    if not families:
        raise ValueError(
            f"Provider module '{module_id}' is not migrated to the AI-first family catalog contract yet."
        )

    print(f"Provider module: {provider_name} ({module_id})")
    print(f"Catalog source: {module_dir}")
    print(f"Total families: {len(families)}")
    print("")
    for family in families:
        family_id = family.get("id", "")
        methods_obj = family.get("methods", [])
        methods = methods_obj if isinstance(methods_obj, list) else []
        path_templates_obj = family.get("path_templates", [])
        path_templates = path_templates_obj if isinstance(path_templates_obj, list) else []
        base_url = family.get("base_url", "")
        description = family.get("description", "")
        method_text = ",".join([str(item) for item in methods]) if methods else "GET"
        path_text = path_templates[0] if path_templates else ""
        print(f"- {family_id} [{method_text}] {base_url}{path_text}")
        print(f"  notes: {description}")
    return 0


def cmd_fetch_sample(args: argparse.Namespace) -> int:
    from sancho.modules import catalog_state_for_module, discover_module_map, install_module

    provider = args.provider.strip() if isinstance(args.provider, str) else ""
    if provider not in ZERO_KEY_PROVIDERS:
        print(
            f"Unknown sample provider '{provider}'. Available: {', '.join(supported_providers())}",
            file=sys.stderr,
        )
        return 2
    workspace_root = _resolve_workspace_arg(args.workspace)
    module_id = provider_to_module_id(provider)
    installed = discover_module_map(workspace_root, zone="source")
    installed_now = False
    if module_id not in installed:
        if not getattr(args, "json", False):
            print(f"Installing {module_id} ...", file=sys.stderr)
        install_module(workspace_root, module_id=module_id)
        installed_now = True
        installed = discover_module_map(workspace_root, zone="source")
    module_ref = installed[module_id]
    catalog_state, catalog_detail = catalog_state_for_module(
        workspace_root, module_id, module_ref.module_dir, module_ref.manifest
    )
    if catalog_state == "not_ready_catalog_missing":
        payload_out = {
            "provider": provider,
            "module_id": module_id,
            "status": "not_ready_catalog_missing",
            "catalog_state": catalog_state,
            "detail": catalog_detail,
            "run_id": None,
            "counts": {"reused": 0, "fetched": 0, "skipped": 1, "failed": 0},
            "next_suggested_command": f"sancho add {module_id} --workspace {args.workspace} --discover",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload_out, indent=2))
        else:
            print(
                f"{module_id} is installed but not ready: {catalog_detail}",
                file=sys.stderr,
            )
            print(f"Try: {payload_out['next_suggested_command']}", file=sys.stderr)
        return 1
    spec = ZERO_KEY_PROVIDERS[provider]
    shape = spec.get("shape", "catalog")
    if shape == "endpoint":
        payload = {"endpoint": spec["endpoint"], "params": spec.get("params", {})}
    else:
        payload = {
            "base": spec["base"],
            "method": spec["method"],
            "path": spec["path"],
            "params": spec.get("params", {}),
            "body": spec.get("body", {}),
        }
    if not getattr(args, "json", False):
        print(f"Fetching sample from {module_id}: {spec['description']}")
    from sancho.runtime.executor import run_module

    result = run_module(workspace_root, module_id=module_id, input_payload=payload)
    output = result.output or {}
    rows = output.get("rows")
    row_count = len(rows) if isinstance(rows, list) else None

    is_json = getattr(args, "json", False)
    cache_status = result.cache_status or ("fetched_api" if result.status == "ok" else "failed")
    public = _auto_public_export(
        workspace_root,
        list(result.record_dirs),
        module_id=module_id,
        labels=[safe_slug(provider)] if result.record_dirs else None,
        unit_sources=[cache_status] if result.record_dirs else None,
        quiet=is_json,
    )

    if not is_json:
        print(f"OK  rows={row_count if row_count is not None else 'n/a'}  module={module_id}")
        _print_primary(public)
        print(
            f"\n    explore further:  sancho fetch catalog {provider} --workspace {args.workspace}",
            file=sys.stderr,
        )
        return 0

    run_id = None
    from sancho.run_log import LOGS_DIRNAME, RUNS_LOG

    runs_path = workspace_root / LOGS_DIRNAME / RUNS_LOG
    if runs_path.exists():
        for line in reversed(runs_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("module_id") == module_id and event.get("event_type") == "run_finished":
                run_id = event.get("run_id")
                break
    reused = 1 if cache_status == "reused_cache" else 0
    fetched = 1 if cache_status == "fetched_api" else 0
    payload_out = {
        "provider": provider,
        "module_id": module_id,
        "status": result.status,
        "catalog_state": catalog_state,
        "run_id": run_id,
        "row_count": row_count,
        "counts": {
            "reused": reused,
            "fetched": fetched,
            "skipped": 0,
            "failed": 0 if result.status == "ok" else 1,
        },
        "installed_module": installed_now,
        "primary_output_path": str(public.primary_path) if public else None,
        "output_paths": [str(p) for p in public.output_paths] if public else [],
        "export_mode": public.mode if public else None,
        "canonical_record_dirs": [str(p) for p in result.record_dirs],
        "next_suggested_command": f"sancho fetch catalog {provider} --workspace {args.workspace}",
    }
    print(json.dumps(payload_out, indent=2, default=str))
    return 0


def _collect_param_types(catalog: dict) -> dict[str, str]:
    """Build a best-effort key->type map by scanning every family's query_params."""
    types: dict[str, str] = {}
    families = catalog.get("families", [])
    if not isinstance(families, list):
        return types
    for family in families:
        if not isinstance(family, dict):
            continue
        qp = family.get("query_params", {})
        if not isinstance(qp, dict):
            continue
        for key, meta in qp.items():
            if not isinstance(key, str) or not isinstance(meta, dict):
                continue
            declared = meta.get("type")
            if isinstance(declared, str) and declared.strip():
                types.setdefault(key, declared.strip())
    return types


def _coerce_param_value(value: str, declared_type: str | None) -> Any:
    stripped = value.strip()
    if declared_type == "string":
        return stripped
    if declared_type in {"int", "float", "number"}:
        try:
            if declared_type == "float":
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped
    if declared_type == "bool":
        if stripped.lower() in {"true", "1", "yes"}:
            return True
        if stripped.lower() in {"false", "0", "no"}:
            return False
        return stripped
    # No declared type: light-touch coercion for booleans only.
    if stripped.lower() == "true":
        return True
    if stripped.lower() == "false":
        return False
    return stripped


def _parse_param_pair(raw: str, type_hints: dict[str, str]) -> tuple[str, Any]:
    if "=" not in raw:
        raise ValueError(f"--param must be key=value (got '{raw}')")
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"--param key is empty (got '{raw}')")
    return key, _coerce_param_value(value, type_hints.get(key))


def _merge_param_pairs(base: dict, pairs: list[str] | None, type_hints: dict[str, str]) -> dict:
    merged = dict(base)
    for pair in pairs or []:
        key, value = _parse_param_pair(pair, type_hints)
        merged[key] = value
    return merged


def cmd_fetch_run(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    body = _load_body_json(args.body)
    module_id, _, catalog = resolve_provider_catalog(workspace_root, args.provider)
    type_hints = _collect_param_types(catalog)
    params = _merge_param_pairs(
        _load_params_json(args.params), getattr(args, "param", None), type_hints
    )
    families_obj = catalog.get("families", [])
    families = [item for item in families_obj if isinstance(item, dict)] if isinstance(families_obj, list) else []
    if not families:
        raise ValueError(
            f"Provider module '{module_id}' is not migrated to the direct request contract yet. "
            "Use a large-tier provider module with catalog families."
        )
    payload = {"method": args.method, "path": args.path, "params": params, "body": body}
    if isinstance(args.base, str) and args.base.strip():
        payload["base"] = args.base
    from sancho.runtime.executor import run_module

    result = run_module(workspace_root, module_id=module_id, input_payload=payload)
    cache_status = result.cache_status or ("fetched_api" if result.status == "ok" else "failed")
    public = _auto_public_export(
        workspace_root,
        list(result.record_dirs),
        module_id=module_id,
        labels=[safe_slug(args.provider)] if result.record_dirs else None,
        unit_sources=[cache_status] if result.record_dirs else None,
        quiet=True,
    )
    summary = {
        "module_id": result.module_id,
        "status": result.status,
        "cache_status": result.cache_status,
        "row_count": _row_count(result.output),
        "primary_output_path": str(public.primary_path) if public else None,
        "output_paths": [str(p) for p in public.output_paths] if public else [],
        "export_mode": public.mode if public else None,
        "canonical_record_dirs": [str(p) for p in result.record_dirs],
    }
    if getattr(args, "full_output", False):
        summary["output"] = result.output
    print(json.dumps(summary, indent=2, default=str))
    if public is not None:
        label = "Primary folder" if public.mode != "single_file" else "Primary file"
        print(f"\n{label}:\n{public.primary_path}", file=sys.stderr)
    return 0
