from __future__ import annotations

import importlib.util
import json
import os
import traceback
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.catalog_cache import resolve_cache_dir
from sancho.config import load_workspace_config
from sancho.env_keys import MODULE_KEYS, load_env_values
from sancho.modules import resolve_module_for_execution
from sancho.repair_packet import write_error_packet
from sancho.run_log import LOGS_DIRNAME, RUNS_LOG, begin_run, finish_run
from sancho.runtime import request_state
from sancho.runtime.contracts import ModuleContext, ModuleRunResult
from sancho.runtime.errors import ModuleExecutionError
from sancho.runtime.redaction import redact_sensitive_text as _redact_secrets
from sancho.runtime.schema import validate_schema
from sancho.runtime.soft_validation import missing_required_keys, required_env_keys, soft_validate_schema


def _import_module_from_path(module_file: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise ModuleExecutionError(f"Could not import module file: {module_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row_count(output: Any) -> int | None:
    if output is None:
        return 0
    if isinstance(output, list):
        return len(output)
    if isinstance(output, dict):
        for key in ("rows", "data", "results", "records"):
            value = output.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def _list_files(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {str(p) for p in root.rglob("*") if p.is_file()}


def _last_successful_run(workspace_root: Path, module_id: str) -> dict[str, Any] | None:
    runs_log = workspace_root / LOGS_DIRNAME / RUNS_LOG
    if not runs_log.exists():
        return None
    last: dict[str, Any] | None = None
    for line in runs_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("module_id") != module_id or event.get("event_type") != "run_finished":
            continue
        if event.get("status") in {"success_with_data", "success_empty"}:
            last = event
    return last


def _docs_links_for(manifest: dict[str, Any]) -> list[str]:
    links: list[str] = []
    sources = manifest.get("sources")
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, str) and url:
                    label = str(item.get("label") or url)
                    links.append(f"{label}: {url}")
    api_key_docs = manifest.get("api_key_docs")
    if isinstance(api_key_docs, str) and api_key_docs.strip():
        links.append(api_key_docs.strip())
    elif isinstance(api_key_docs, list):
        links.extend(str(item).strip() for item in api_key_docs if isinstance(item, str) and item.strip())
    elif isinstance(api_key_docs, dict):
        links.extend(str(item).strip() for item in api_key_docs.values() if isinstance(item, str) and item.strip())
    return links


def _api_key_hint(manifest: dict[str, Any], missing_keys: list[str]) -> str:
    api_key_docs = manifest.get("api_key_docs")
    links: list[str] = []
    if isinstance(api_key_docs, str) and api_key_docs.strip():
        links.append(api_key_docs.strip())
    elif isinstance(api_key_docs, list):
        links.extend(str(item).strip() for item in api_key_docs if isinstance(item, str) and item.strip())
    elif isinstance(api_key_docs, dict):
        for key in missing_keys:
            value = api_key_docs.get(key)
            if isinstance(value, str) and value.strip():
                links.append(value.strip())
    if not links:
        return ""
    return " Get the key here: " + ", ".join(links) + "."


def _safe_retry_command(module_id: str, workspace_root: Path) -> str:
    return f"sancho run {module_id} --workspace {workspace_root}"


def _suggested_override_path(workspace_root: Path, module_type: str, module_id: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in module_id)
    return str(workspace_root / "custom" / module_type / slug)


def _http_meta_from_exception(exc: BaseException) -> tuple[int | None, str | None, str | None]:
    """Best-effort: pull HTTP status, response excerpt, and resolved URL."""
    try:
        import requests  # local import -- only needed in error branches
    except Exception:
        return None, None, None
    if isinstance(exc, requests.exceptions.HTTPError) and getattr(exc, "response", None) is not None:
        resp = exc.response
        status = getattr(resp, "status_code", None)
        text = _redact_secrets(getattr(resp, "text", "") or "")
        url = _redact_secrets(getattr(resp, "url", None))
        return status, text, url
    return None, None, None


def _build_context(workspace_root: Path, config: dict[str, Any], env: dict[str, str]) -> ModuleContext:
    fetched_data_path = workspace_root / "fetched-data"
    analysis_data_path = workspace_root / "analysis-data"
    outputs_path = workspace_root / "outputs"
    return ModuleContext(
        workspace_root=workspace_root,
        data_raw_path=fetched_data_path,
        data_refined_path=analysis_data_path,
        data_outputs_path=outputs_path,
        env=env,
        runtime=config.get("runtime", {}),
        catalog_cache_dir=resolve_cache_dir(config),
        storage=config.get("storage", {}) or {},
        fetched_data_path=fetched_data_path,
        analysis_data_path=analysis_data_path,
        logs_path=workspace_root / "logs",
        update_backups_path=workspace_root / "update-backups",
    )


def _packet_kwargs(
    workspace_root: Path,
    manifest: dict[str, Any],
    module_id: str,
    fetched_data_path: Path,
    files_before: set[str],
    exc: BaseException | None = None,
) -> dict[str, Any]:
    files_after = _list_files(fetched_data_path)
    new_files = sorted(files_after - files_before)
    status, response_excerpt, url = (None, None, None)
    if exc is not None:
        status, response_excerpt, url = _http_meta_from_exception(exc)
    return {
        "files_written": new_files,
        "last_successful_run": _last_successful_run(workspace_root, module_id),
        "docs_links": _docs_links_for(manifest),
        "suggested_override_path": _suggested_override_path(
            workspace_root, str(manifest.get("type") or "fetch"), module_id
        ),
        "safe_retry_command": _safe_retry_command(module_id, workspace_root),
        "http_status": status,
        "response_excerpt": response_excerpt,
        "resolved_url": url,
    }


def run_module(workspace_root: Path, module_id: str, input_payload: dict[str, Any] | None = None) -> ModuleRunResult:
    module_ref = resolve_module_for_execution(workspace_root, module_id)
    module_manifest = module_ref.manifest

    entrypoint = str(module_manifest["entrypoint"])
    if ":" not in entrypoint:
        raise ModuleExecutionError(f"Invalid entrypoint format '{entrypoint}', expected file.py:function")
    file_name, function_name = entrypoint.split(":", 1)
    module_file = module_ref.module_dir / file_name

    if not module_file.exists():
        raise ModuleExecutionError(f"Entrypoint file does not exist: {module_file}")

    config = load_workspace_config(workspace_root)
    env_values = load_env_values(workspace_root)
    env = {**env_values, **os.environ}
    declared_env_names = sorted(set(required_env_keys(module_manifest) + MODULE_KEYS.get(module_id, [])))

    context = _build_context(workspace_root, config, env)

    fetched_data_path = context.fetched_data_path or (workspace_root / "fetched-data")
    files_before = _list_files(fetched_data_path)

    soft_warnings = soft_validate_schema(
        input_payload or {}, module_manifest.get("input_schema"), label="module input"
    )
    if soft_warnings:
        for warning in soft_warnings:
            print(f"[soft-validate] {warning}")

    run_handle = begin_run(
        workspace_root,
        module_id=module_id,
        module_source=module_ref.zone if hasattr(module_ref, "zone") else "source",
        module_version=str(module_manifest.get("version", "")),
        module_path=str(module_file),
        request_summary=input_payload or {},
        env_names=[name for name in declared_env_names if env.get(name)],
    )

    # HARD CHECK: required API keys declared by the manifest must be present.
    missing_keys = missing_required_keys(module_manifest, env)
    if missing_keys:
        message = (
            f"Module '{module_id}' declares required API key(s) "
            f"that are missing: {', '.join(missing_keys)}. "
            "Add them with `sancho env open` and re-run."
            f"{_api_key_hint(module_manifest, missing_keys)}"
        )
        packet = write_error_packet(
            run_handle,
            error_message=message,
            **_packet_kwargs(workspace_root, module_manifest, module_id, fetched_data_path, files_before),
        )
        finish_run(
            run_handle,
            status="skipped_needs_key",
            error_message=message,
            repair_packet_path=str(packet),
        )
        raise ModuleExecutionError(message)

    module = _import_module_from_path(module_file, module_name=f"sancho_runtime_{module_id.replace('.', '_')}")
    fn = getattr(module, function_name, None)
    if fn is None:
        raise ModuleExecutionError(f"Entrypoint function '{function_name}' was not found in {module_file}")

    previous_storage = request_state.get_storage()
    request_state.set_storage(config.get("storage", {}) or {})
    request_state.set_run_provenance(
        module_version=str(module_manifest.get("version", "")),
        sancho_version=SANCHO_VERSION,
        module_source=module_ref.zone if hasattr(module_ref, "zone") else "source",
        module_path=str(module_file),
    )
    try:
        output = fn(context=context, payload=input_payload or {})
    except ModuleExecutionError as exc:
        message = _redact_secrets(str(exc)) or str(exc)
        packet = write_error_packet(
            run_handle,
            error_message=message,
            exception_text=_redact_secrets(traceback.format_exc()),
            **_packet_kwargs(workspace_root, module_manifest, module_id, fetched_data_path, files_before, exc=exc),
        )
        finish_run(
            run_handle,
            status="failed",
            error_message=message,
            repair_packet_path=str(packet),
        )
        raise ModuleExecutionError(message) from exc
    except Exception as exc:
        status, _, _ = _http_meta_from_exception(exc)
        if status in (401, 403):
            message = (
                f"Module '{module_id}' received HTTP {status}. "
                "This usually means an API key is missing or invalid. "
                "Check your .env file."
            )
            packet = write_error_packet(
                run_handle,
                error_message=message,
                exception_text=_redact_secrets(traceback.format_exc()),
                extra={"http_status_hint": status},
                **_packet_kwargs(workspace_root, module_manifest, module_id, fetched_data_path, files_before, exc=exc),
            )
            finish_run(
                run_handle,
                status="skipped_needs_key",
                error_message=message,
                repair_packet_path=str(packet),
            )
            raise ModuleExecutionError(message) from exc
        wrapped = f"Module '{module_id}' failed: {_redact_secrets(str(exc)) or str(exc)}"
        packet = write_error_packet(
            run_handle,
            error_message=wrapped,
            exception_text=_redact_secrets(traceback.format_exc()),
            **_packet_kwargs(workspace_root, module_manifest, module_id, fetched_data_path, files_before, exc=exc),
        )
        finish_run(
            run_handle,
            status="failed",
            error_message=wrapped,
            repair_packet_path=str(packet),
        )
        raise ModuleExecutionError(wrapped) from exc
    finally:
        request_state.set_storage(previous_storage)

    soft_output_warnings = soft_validate_schema(
        output, module_manifest.get("output_schema"), label="module output"
    )
    for warning in soft_output_warnings:
        print(f"[soft-validate] {warning}")

    rows = _row_count(output)
    finish_run(
        run_handle,
        status="success_with_data" if rows else "success_empty",
        row_count=rows,
    )
    return ModuleRunResult(module_id=module_id, status="ok", output=output)


def run_playbook(workspace_root: Path, playbook_path: Path) -> list[ModuleRunResult]:
    import yaml

    payload = yaml.safe_load(playbook_path.read_text(encoding="utf-8")) or {}
    steps = payload.get("steps", [])
    results: list[ModuleRunResult] = []
    for step in steps:
        module_id = step["module"]
        module_input = step.get("input", {})
        results.append(run_module(workspace_root, module_id=module_id, input_payload=module_input))
    return results
