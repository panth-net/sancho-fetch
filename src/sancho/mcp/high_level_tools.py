"""Phase 10 high-level MCP tools.

Wraps the Phase 2-9 CLI surfaces so Claude Desktop / ChatGPT / Cursor can
drive Sancho without exposing the 100+ provider-specific tools as the
primary UX. Local-only -- hosted MCP (``policy.stateless=True``) skips
these because the hosted sampler cannot access the user's workspace.
"""

from __future__ import annotations

from sancho.mcp.high_level_handlers import (
    CacheStatusHandler,
    CustomStatusHandler,
    EnvOpenHandler,
    EnvRecommendHandler,
    ExportToProjectHandler,
    FetchRunHandler,
    FetchedDataAuditHandler,
    LogShowHandler,
    LogTailHandler,
    ModeHandler,
    ModuleShowHandler,
    UpdateCheckHandler,
    UpdatePreviewHandler,
    handle_find_sources,
    handle_inventory,
    handle_paths,
)
from sancho.mcp.models import MCPContext, ToolSpec


def build_high_level_tools(ctx: MCPContext) -> list[ToolSpec]:
    if ctx.policy.stateless:
        return []
    return [
        ToolSpec(
            name="sancho_paths",
            description="Return every relevant Sancho Fetch path (workspace, source, fetched-data, logs, env, library).",
            input_schema={"type": "object"},
            handler=handle_paths,
        ),
        ToolSpec(
            name="sancho_mode",
            description="Return only the Sancho developer-mode boolean without exposing .env contents.",
            input_schema={"type": "object"},
            handler=ModeHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_inventory",
            description="List built-in starter packs and fetch providers.",
            input_schema={"type": "object"},
            handler=handle_inventory,
        ),
        ToolSpec(
            name="sancho_find_sources",
            description="Rank module candidates for a natural-language query.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "type": {"type": "string"},
                },
            },
            handler=handle_find_sources,
        ),
        ToolSpec(
            name="sancho_module_show",
            description="Inspect one module: manifest, schema, override status, last run.",
            input_schema={
                "type": "object",
                "required": ["module_id"],
                "properties": {"module_id": {"type": "string"}},
            },
            handler=ModuleShowHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_cache_status",
            description="Report cache status for a module or a specific request.",
            input_schema={
                "type": "object",
                "required": ["module_id"],
                "properties": {
                    "module_id": {"type": "string"},
                    "request": {"type": "object"},
                    "max_age_seconds": {"type": "integer"},
                },
            },
            handler=CacheStatusHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_fetch_run",
            description="Execute one fetch module with the given input payload.",
            input_schema={
                "type": "object",
                "required": ["module_id"],
                "properties": {
                    "module_id": {"type": "string"},
                    "input": {"type": "object"},
                },
            },
            handler=FetchRunHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_export_to_project",
            description="Copy a cached record into a project's 'sancho-fetched-data/' folder.",
            input_schema={
                "type": "object",
                "required": ["cache_record"],
                "properties": {
                    "cache_record": {"type": "string"},
                    "project": {"type": "string"},
                    "label": {"type": "string"},
                },
            },
            handler=ExportToProjectHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_log_tail",
            description="Tail recent run/error events from logs/runs.jsonl (or errors.jsonl).",
            input_schema={
                "type": "object",
                "properties": {
                    "errors": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "module_id": {"type": "string"},
                },
            },
            handler=LogTailHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_log_show",
            description="Show every event + repair packet for one run_id.",
            input_schema={
                "type": "object",
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
            },
            handler=LogShowHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_env_open",
            description="Surface the .env path and which env vars a provider needs. Never reads values.",
            input_schema={
                "type": "object",
                "properties": {"provider": {"type": "string"}},
            },
            handler=EnvOpenHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_env_recommend",
            description=(
                "Given a natural-language description of the data the user wants, "
                "return ranked provider candidates with the env-var NAMES they need "
                "and which of those are missing in the user's .env. "
                "Values are never read or printed -- only names + missing status + sign-up URLs."
            ),
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            handler=EnvRecommendHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_update_check",
            description="Non-mutating status report: module versions, local edits, custom overrides, gitignore, .env presence.",
            input_schema={"type": "object"},
            handler=UpdateCheckHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_update_preview",
            description="Per-module preview with risk and recommended action.",
            input_schema={
                "type": "object",
                "properties": {"module_id": {"type": "string"}},
            },
            handler=UpdatePreviewHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_custom_status",
            description="List custom modules and whether upstream is newer than each override.",
            input_schema={"type": "object"},
            handler=CustomStatusHandler(workspace_root=ctx.workspace_root),
        ),
        ToolSpec(
            name="sancho_fetched_data_audit",
            description="Find fetched-data records produced by older module versions.",
            input_schema={"type": "object"},
            handler=FetchedDataAuditHandler(workspace_root=ctx.workspace_root),
        ),
    ]
