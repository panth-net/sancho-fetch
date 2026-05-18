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
from sancho.project_export import export_record_to_project
from sancho.run_log import ERRORS_LOG, LOGS_DIRNAME, RUNS_LOG
from sancho.templates.runtime.cache_index import iter_cache_records
from sancho.update_engine import check_updates, preview_updates_rich


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


def handle_inventory(arguments: dict[str, Any]) -> Any:
    _ = arguments
    return _inventory_payload()


def handle_find_sources(arguments: dict[str, Any]) -> Any:
    query = str(arguments.get("query", "") or "").strip()
    if not query:
        raise ValueError("sancho_find_sources requires arguments.query")
    limit = int(arguments.get("limit") or 12)
    type_filter = str(arguments.get("type") or "fetch")
    candidates = find_sources(query, limit=limit, type_filter=type_filter)
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
        return {"module_id": module_id, "status": result.status, "output": result.output}


@dataclass
class ExportToProjectHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        record_id = str(arguments.get("cache_record") or arguments.get("record_id") or "").strip()
        if not record_id:
            raise ValueError("sancho_export_to_project requires arguments.cache_record")
        project_obj = arguments.get("project")
        project_root = Path(str(project_obj)).resolve() if project_obj else Path.cwd().resolve()
        record_dir = _find_cache_record_dir(self.workspace_root, record_id)
        if record_dir is None:
            raise ValueError(f"No cache record matched: {record_id}")
        label_obj = arguments.get("label")
        label = str(label_obj) if isinstance(label_obj, str) and label_obj.strip() else None
        result = export_record_to_project(
            record_dir=record_dir,
            project_root=project_root,
            workspace_root=self.workspace_root,
            label=label,
        )
        return {
            "bundle_dir": str(result.bundle_dir),
            "mode": result.mode,
            "record_dirs": [str(p) for p in result.record_dirs],
            "bytes_written": result.bytes_written,
        }


@dataclass
class LogTailHandler:
    workspace_root: Path

    def __call__(self, arguments: dict[str, Any]) -> Any:
        errors_only = bool(arguments.get("errors"))
        limit = int(arguments.get("limit") or 20)
        module_filter_obj = arguments.get("module_id")
        module_filter = str(module_filter_obj).strip() if isinstance(module_filter_obj, str) and module_filter_obj.strip() else None
        target = self.workspace_root / LOGS_DIRNAME / (ERRORS_LOG if errors_only else RUNS_LOG)
        events = _read_jsonl(target)
        if module_filter:
            events = [e for e in events if e.get("module_id") == module_filter]
        return {
            "log_file": str(target),
            "events": events[-limit:],
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
        from sancho.env_keys import provider_key_hints
        provider = str(arguments.get("provider") or "").strip()
        env_path = self.workspace_root / ".env"
        env_example = self.workspace_root / ".env.example"
        hints = provider_key_hints(provider) if provider else []
        return {
            "env_path": str(env_path),
            "env_exists": env_path.exists(),
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
