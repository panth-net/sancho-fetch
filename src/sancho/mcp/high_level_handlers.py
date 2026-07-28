"""Handler classes for the Phase 10 high-level MCP tools.

Implemented as callable dataclasses (mirroring the pattern in
:mod:`sancho.mcp.tool_specs`) so each handler has explicit types and no
nested function definitions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sancho.cli_cache import (
    _fetched_data_root,
    _status_for_module,
    _status_for_request,
)
from sancho.cli_custom import _custom_status_payload
from sancho.cli_fetched_data import audit_old_modules
from sancho.cli_find import find_sources
from sancho.cli_inventory import _inventory_payload
from sancho.cli_library import _paths_payload
from sancho.cli_mode import developer_mode
from sancho.cli_module_inspect import _module_payload
from sancho.cli_public_export import auto_public_export as _public_export, row_count as _row_count
from sancho.config import load_workspace_config
from sancho.project_export import export_records_to_public_outputs
from sancho.run_log import ERRORS_LOG, LOGS_DIRNAME, RUNS_LOG, tail_events_view
from sancho.runtime.contracts import ModuleRunResult
from sancho.templates.runtime.cache_index import iter_cache_records
from sancho.update_engine import check_updates, preview_updates_rich


# MCP tool results land verbatim in the model's context window, so fetched
# data is never returned -- the exported working file holds it. Callers get a
# capped preview: enough to see the shape and answer a quick question.
_PREVIEW_MAX_ROWS = 20
_PREVIEW_MAX_CHARS = 4_000


def _output_preview(output: Any) -> Any:
    if output is None:
        return None
    preview: Any = output
    if isinstance(output, list):
        preview = output[:_PREVIEW_MAX_ROWS]
    elif isinstance(output, dict):
        # Cap every top-level list, not just "rows": raw API passthroughs keep
        # their data under provider-specific keys ("observations", "features",
        # ...), and serializing the whole payload just to truncate it below
        # would burn CPU and memory proportional to the fetch size.
        preview = {
            key: value[:_PREVIEW_MAX_ROWS] if isinstance(value, list) else value
            for key, value in output.items()
        }
    text = json.dumps(preview, default=str)
    if len(text) <= _PREVIEW_MAX_CHARS:
        return preview
    return text[:_PREVIEW_MAX_CHARS]


def run_result_summary(workspace_root: Path, module_id: str, result: ModuleRunResult) -> dict[str, Any]:
    """The one return contract for every MCP fetch tool."""
    cache_status = result.cache_status or ("fetched_api" if result.status == "ok" else "failed")
    # quiet=True keeps stderr clean for the MCP transport; the export + failure
    # events still land in runs.jsonl, which also lets cache-hit re-runs find
    # and reuse this export instead of regenerating the file.
    public = _public_export(
        workspace_root,
        list(result.record_dirs),
        module_id=module_id,
        unit_sources=[cache_status] if result.record_dirs else None,
        quiet=True,
    )
    if public is not None:
        note = "output_preview is truncated. The full dataset is the file at primary_output_path."
    elif result.status == "ok":
        note = (
            "output_preview is truncated. No working file was exported for this "
            "run; use sancho_export_to_project to write one from the cache record."
        )
    else:
        note = "Run failed -- no output file was written. Check the error and sancho_log_tail."
    return {
        "module_id": module_id,
        "status": result.status,
        "cache_status": cache_status,
        "row_count": _row_count(result.output),
        "output_preview": _output_preview(result.output),
        "primary_output_path": str(public.primary_path) if public else None,
        "output_paths": [str(p) for p in public.output_paths] if public else [],
        "export_mode": public.mode if public else None,
        "counts": {
            "reused": int(cache_status == "reused_cache"),
            "fetched": int(cache_status == "fetched_api"),
            "skipped": 0,
            "failed": 0 if result.status == "ok" else 1,
        },
        "note": note,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _find_cache_record_dir(workspace_root: Path, record_id: str) -> Path | None:
    parts = record_id.strip("/").split("/")
    root = _fetched_data_root(workspace_root)
    if len(parts) == 4:
        candidate = root / parts[0] / parts[1] / parts[2] / parts[3]
        return candidate if candidate.exists() else None
    if len(parts) == 1:
        for row in iter_cache_records(root):
            if row["request_key"] == parts[0] or row["record_id"].endswith(parts[0]):
                return Path(row["record_dir"])
    return None


def handle_paths(arguments: dict[str, Any]) -> Any:
    _ = arguments
    return _paths_payload()


@dataclass
class InventoryHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        _ = arguments
        return _inventory_payload(self.workspace_root)


@dataclass
class FindSourcesHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        query = str(arguments.get("query", "") or "").strip()
        if not query:
            raise ValueError("sancho_find_sources requires arguments.query")
        limit = int(arguments.get("limit") or 12)
        type_filter = str(arguments.get("type") or "fetch")
        candidates = find_sources(
            query, limit=limit, type_filter=type_filter, workspace_root=self.workspace_root
        )
        return {
            "query": query,
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "id": c.module_id,
                    "module_id": c.module_id,
                    "kind": c.kind,
                    "score": c.score,
                    "reasons": c.reasons,
                    "member_count": c.member_count,
                    "description": c.description,
                    **({"coverage": c.coverage} if c.coverage else {}),
                }
                for c in candidates
            ],
            "note": (
                "Candidates only. Claude/Codex decides the final plan. "
                "When a 'pack' candidate scores well, prefer installing the "
                "pack (one `sancho add pack.<name>` call) over picking "
                "individual modules."
            ),
        }


@dataclass
class ModuleShowHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        module_id = str(arguments.get("module_id", "") or "").strip()
        if not module_id:
            raise ValueError("sancho_module_show requires arguments.module_id")
        payload = _module_payload(self.workspace_root, module_id)
        if payload is None:
            raise ValueError(f"Module not found: {module_id}")
        return payload


@dataclass
class CacheStatusHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        module_id = str(arguments.get("module_id", "") or "").strip()
        if not module_id:
            raise ValueError("sancho_cache_status requires arguments.module_id")
        max_age_obj = arguments.get("max_age_seconds")
        max_age: int | None = None
        if isinstance(max_age_obj, (int, float, str)) and str(max_age_obj).strip():
            max_age = int(max_age_obj)
        request = arguments.get("request")
        if isinstance(request, dict):
            return _status_for_request(self.workspace_root, module_id, request, max_age)
        return _status_for_module(self.workspace_root, module_id, max_age)


@dataclass
class FetchRunHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        from sancho.runtime.executor import run_module
        module_id = str(arguments.get("module_id", "") or "").strip()
        if not module_id:
            raise ValueError("sancho_fetch_run requires arguments.module_id")
        input_obj = arguments.get("input")
        if input_obj is None:
            input_payload: dict[str, Any] = {}
        elif isinstance(input_obj, dict):
            input_payload = input_obj
        else:
            raise ValueError("sancho_fetch_run arguments.input must be an object")
        result = run_module(self.workspace_root, module_id=module_id, input_payload=input_payload)
        return run_result_summary(self.workspace_root, module_id, result)


@dataclass
class ExportToProjectHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        record_arg = arguments.get("cache_record") or arguments.get("record_id")
        record_ids: list[str]
        if isinstance(record_arg, list):
            record_ids = [str(r).strip() for r in record_arg if str(r).strip()]
        elif isinstance(record_arg, str) and record_arg.strip():
            record_ids = [record_arg.strip()]
        else:
            record_ids = []
        if not record_ids:
            raise ValueError("sancho_export_to_project requires arguments.cache_record")

        project_obj = arguments.get("project")
        project_root = Path(str(project_obj)).resolve() if project_obj else Path.cwd().resolve()

        record_dirs: list[Path] = []
        for record_id in record_ids:
            record_dir = _find_cache_record_dir(self.workspace_root, record_id)
            if record_dir is None:
                raise ValueError(f"No cache record matched: {record_id}")
            record_dirs.append(record_dir)

        label_obj = arguments.get("label")
        labels = (
            [str(label_obj)]
            if isinstance(label_obj, str) and label_obj.strip() and len(record_dirs) == 1
            else None
        )
        config = load_workspace_config(self.workspace_root)
        result = export_records_to_public_outputs(
            record_dirs=record_dirs,
            project_root=project_root,
            workspace_root=self.workspace_root,
            labels=labels,
            config=config,
            unit_sources=["reused_cache"] * len(record_dirs),
        )
        return {
            "primary_output_path": str(result.primary_path),
            "output_paths": [str(p) for p in result.output_paths],
            "mode": result.mode,
            "canonical_record_dirs": [str(p) for p in result.canonical_record_dirs],
        }


@dataclass
class LogTailHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        errors_only = bool(arguments.get("errors"))
        # A zero/negative limit would slice from the wrong end of the list.
        # Default 10: the last ~3-4 runs, enough to answer "did my recent runs
        # succeed" -- callers pass a bigger limit when they want history.
        limit = max(1, int(arguments.get("limit") or 10))
        module_filter_obj = arguments.get("module_id")
        module_filter = str(module_filter_obj).strip() if isinstance(module_filter_obj, str) and module_filter_obj.strip() else None
        target = self.workspace_root / LOGS_DIRNAME / (ERRORS_LOG if errors_only else RUNS_LOG)
        events = _read_jsonl(target)
        if module_filter:
            events = [e for e in events if e.get("module_id") == module_filter]
        return {
            "log_file": str(target),
            "events": tail_events_view(events[-limit:]),
            "event_count": len(events),
        }


@dataclass
class LogShowHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        run_id = str(arguments.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("sancho_log_show requires arguments.run_id")
        events = [
            e for e in _read_jsonl(self.workspace_root / LOGS_DIRNAME / RUNS_LOG)
            if e.get("run_id") == run_id
        ]
        repair_packet_text: str | None = None
        if events:
            packet_path_obj = events[-1].get("repair_packet_path")
            if isinstance(packet_path_obj, str) and Path(packet_path_obj).exists():
                repair_packet_text = Path(packet_path_obj).read_text(encoding="utf-8")
        return {"run_id": run_id, "events": events, "repair_packet": repair_packet_text}


@dataclass
class EnvOpenHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        from sancho.env_keys import env_status, provider_key_hints
        provider = str(arguments.get("provider") or "").strip()
        status = env_status(self.workspace_root)
        env_path = Path(str(status["env_path"]))
        env_example = self.workspace_root / ".env.example"
        hints = provider_key_hints(provider) if provider else []
        return {
            "env_path": str(env_path),
            "env_exists": env_path.exists(),
            "env_paths": status["env_paths"],
            "workspace_env_path": status["workspace_env_path"],
            "env_example_path": str(env_example),
            "env_example_exists": env_example.exists(),
            "provider": provider,
            "provider_key_hints": hints,
            "note": "Agents do not modify .env. Show the user the path and which keys are needed.",
        }


@dataclass
class ModeHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        _ = arguments
        return {"developer_mode": developer_mode(str(self.workspace_root))}


@dataclass
class EnvRecommendHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        from sancho.env_keys import env_recommend
        query = str(arguments.get("query", "") or "").strip()
        if not query:
            raise ValueError("sancho_env_recommend requires arguments.query")
        limit = int(arguments.get("limit") or 8)
        return env_recommend(self.workspace_root, query, limit=limit)


@dataclass
class UpdateCheckHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        _ = arguments
        return check_updates(self.workspace_root)


@dataclass
class UpdatePreviewHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        module_id_obj = arguments.get("module_id")
        module_id: str | None = None
        if isinstance(module_id_obj, str) and module_id_obj.strip():
            module_id = module_id_obj.strip()
        return preview_updates_rich(self.workspace_root, module_id=module_id)


@dataclass
class CustomStatusHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        _ = arguments
        return _custom_status_payload(self.workspace_root)


@dataclass
class FetchedDataAuditHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        _ = arguments
        return audit_old_modules(self.workspace_root)
