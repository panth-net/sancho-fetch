from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sancho.cli_hints import ZERO_KEY_PROVIDERS, supported_providers
from sancho.provider_kits import provider_to_module_id, resolve_provider_catalog
from sancho.runtime.executor import run_module
from sancho.templates.runtime.cache_index import iter_cache_records
from sancho.workspace import find_workspace_root


def _auto_bundle(workspace_root: Path, module_id: str, *, quiet: bool = False) -> None:
    """Drop a sancho-fetched-data bundle in CWD if CWD is outside the library repo."""
    try:
        from sancho.cli_workspace_commands import _maybe_export_project_bundle

        if quiet:
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()):
                _maybe_export_project_bundle(workspace_root, module_id)
        else:
            _maybe_export_project_bundle(workspace_root, module_id)
    except Exception as exc:
        from sancho.run_log import record_run_event

        record_run_event(
            workspace_root,
            event_type="project_bundle_failed",
            module_id=module_id,
            detail={"project_root": str(Path.cwd().resolve()), "error_message": str(exc)},
        )
        if not quiet:
            print(f"[bundle] skipped: {exc}", file=sys.stderr)


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
    before_records = list(iter_cache_records(workspace_root / "fetched-data"))
    result = run_module(workspace_root, module_id=module_id, input_payload=payload)
    after_records = list(iter_cache_records(workspace_root / "fetched-data"))
    output = result.output or {}
    rows = output.get("rows")
    row_count = len(rows) if isinstance(rows, list) else None
    new_records = [
        row for row in after_records
        if row.get("record_id") not in {before.get("record_id") for before in before_records}
    ]
    bundle_before = set(Path.cwd().glob("sancho-fetched-data/*"))
    if not getattr(args, "json", False):
        print(f"OK  rows={row_count if row_count is not None else 'n/a'}  module={module_id}")
        print(f"    saved to fetched-data/{module_id}/... under your workspace")
        print(f"    explore further:  sancho fetch catalog {provider} --workspace {args.workspace}")
    _auto_bundle(workspace_root, module_id, quiet=getattr(args, "json", False))
    bundle_after = set(Path.cwd().glob("sancho-fetched-data/*"))
    if getattr(args, "json", False):
        run_id = None
        latest_records = [row for row in after_records if row.get("module_id") == module_id]
        latest_records.sort(key=lambda row: str(row.get("fetched_at", "")), reverse=True)
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
        payload_out = {
            "provider": provider,
            "module_id": module_id,
            "status": result.status,
            "catalog_state": catalog_state,
            "run_id": run_id,
            "row_count": row_count,
            "counts": {
                "reused": 0,
                "fetched": 1 if result.status == "ok" else 0,
                "skipped": 0,
                "failed": 0 if result.status == "ok" else 1,
            },
            "installed_module": installed_now,
            "cache_records_written": [row.get("record_dir") for row in new_records],
            "latest_record": latest_records[0] if latest_records else None,
            "project_bundles_written": [str(path) for path in sorted(bundle_after - bundle_before)],
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
    result = run_module(workspace_root, module_id=module_id, input_payload=payload)
    print(json.dumps(result.__dict__, indent=2, default=str))
    _auto_bundle(workspace_root, module_id)
    return 0
