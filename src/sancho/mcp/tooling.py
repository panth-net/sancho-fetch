from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sancho import __version__
from sancho.catalog_cache import resolve_cache_dir
from sancho.catalog_tiers import is_large_tier
from sancho.config import load_workspace_config
from sancho.mcp.models import FamilyAliasBinding, MCPContext, MCPPolicy, ToolSpec
from sancho.mcp.high_level_tools import build_high_level_tools
from sancho.mcp.tool_specs import (
    family_alias_tool_spec,
    gov_catalog_tool_spec,
    gov_fetch_tool_spec,
    module_tool_spec,
)
from sancho.modules import ModuleLocation, discover_modules
from sancho.provider_kits import load_provider_catalog

_ALIAS_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")
_ALIAS_SAFE_RE = re.compile(r"[^a-z0-9]+")


def _build_context(
    *,
    workspace_root: Path,
    policy: MCPPolicy | None,
    quick_mode: bool,
    quick_profile: str | None,
    quick_targets: list[str] | tuple[str, ...] | None,
    quick_modules: list[str] | tuple[str, ...] | None,
) -> MCPContext:
    return MCPContext(
        workspace_root=workspace_root,
        policy=policy or MCPPolicy(),
        quick_mode=quick_mode,
        quick_profile=quick_profile,
        quick_targets=tuple(quick_targets or ()),
        quick_modules=tuple(quick_modules or ()),
    )


def _json_text(value: Any) -> str:
    return json.dumps(value, default=str)


def _provider_from_module_id(module_id: str) -> str:
    if module_id.startswith("fetch."):
        return module_id[len("fetch.") :]
    return module_id


def _slug_token(raw: str) -> str:
    slug = _ALIAS_SAFE_RE.sub("_", raw.strip().lower()).strip("_")
    return slug or "family"


def _first_string_list(payload: dict[str, Any], key: str, *, upper: bool = False) -> list[str]:
    values_obj = payload.get(key, [])
    if not isinstance(values_obj, list):
        return []
    values = [str(item).strip() for item in values_obj if isinstance(item, str) and str(item).strip()]
    if upper:
        return [value.upper() for value in values]
    return values


def _is_module_allowed(ctx: MCPContext, module: ModuleLocation) -> bool:
    if ctx.policy.fetch_only and module.type != "fetch":
        return False
    allowlist = ctx.policy.allowlisted_module_ids
    if allowlist is not None and module.id not in allowlist:
        return False
    return True


def _discover_exposed_modules(ctx: MCPContext) -> list[ModuleLocation]:
    modules: list[ModuleLocation] = []
    for module in discover_modules(ctx.workspace_root):
        if module.zone not in {"source", "custom"}:
            continue
        if not _is_module_allowed(ctx, module):
            continue
        modules.append(module)
    return modules


def _build_family_alias_bindings(
    modules: list[ModuleLocation],
    *,
    cache_root: Path | None = None,
) -> list[FamilyAliasBinding]:
    aliases: list[FamilyAliasBinding] = []
    used_names: set[str] = set()
    for module in sorted(modules, key=lambda item: item.id):
        if module.type != "fetch":
            continue
        if not is_large_tier(module.manifest):
            continue

        try:
            catalog = load_provider_catalog(
                module.module_dir, cache_root=cache_root, module_id=module.id
            )
        except Exception:
            continue

        families_obj = catalog.get("families", [])
        if not isinstance(families_obj, list):
            continue

        provider = _provider_from_module_id(module.id)
        provider_slug = _slug_token(provider)
        for family in families_obj:
            if not isinstance(family, dict):
                continue
            templates = _first_string_list(family, "path_templates")
            if not templates:
                continue
            methods = _first_string_list(family, "methods", upper=True)
            bases = _first_string_list(family, "base_aliases")

            family_id = str(family.get("id", "")).strip() or "family"
            family_slug = _slug_token(family_id)
            base_name = f"gov_{provider_slug}__{family_slug}"
            alias_name = base_name
            index = 2
            while alias_name in used_names:
                alias_name = f"{base_name}_{index}"
                index += 1
            used_names.add(alias_name)

            path_template = templates[0]
            path_vars = tuple(dict.fromkeys(_ALIAS_PLACEHOLDER_RE.findall(path_template)))
            aliases.append(
                FamilyAliasBinding(
                    name=alias_name,
                    provider=provider,
                    module_id=module.id,
                    family_id=family_id,
                    method=methods[0] if methods else "GET",
                    base=bases[0] if bases else "",
                    path_template=path_template,
                    path_vars=path_vars,
                )
            )
    return aliases


def _tool_inventory(ctx: MCPContext) -> tuple[dict[str, ToolSpec], list[ModuleLocation], list[FamilyAliasBinding]]:
    modules = _discover_exposed_modules(ctx)
    registry: dict[str, ToolSpec] = {}
    for module in modules:
        registry[module.id] = module_tool_spec(ctx, module)

    aliases: list[FamilyAliasBinding] = []
    if ctx.quick_mode:
        try:
            cache_root = resolve_cache_dir(load_workspace_config(ctx.workspace_root))
        except Exception:
            cache_root = None
        aliases = _build_family_alias_bindings(modules, cache_root=cache_root)
        registry["gov_catalog"] = gov_catalog_tool_spec(ctx, modules, aliases)
        registry["gov_fetch"] = gov_fetch_tool_spec(ctx, modules)
        for alias in aliases:
            registry[alias.name] = family_alias_tool_spec(ctx, alias)

    # Phase 10: high-level workspace/cache/log/update tools. Skipped when
    # ctx.policy.stateless is True (hosted MCP) because those endpoints
    # cannot access the user's workspace.
    for tool in build_high_level_tools(ctx):
        registry[tool.name] = tool

    return registry, modules, aliases


def _tools_payload(ctx: MCPContext) -> dict[str, Any]:
    registry, _, _ = _tool_inventory(ctx)
    tools: list[dict[str, Any]] = []
    for tool_name in sorted(registry):
        tool = registry[tool_name]
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
        )
    return {"tools": tools}


def _handle_method(ctx: MCPContext, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
    params = params or {}
    if method == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": "2026-03-26",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "sancho-mcp", "version": __version__},
        }
        if ctx.policy.instructions:
            result["instructions"] = ctx.policy.instructions
        return result
    if method == "ping":
        return {}
    if method == "tools/list":
        return _tools_payload(ctx)
    if method == "tools/call":
        name = params.get("name")
        arguments_obj = params.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tools/call requires params.name")
        if arguments_obj is None:
            arguments = {}
        elif isinstance(arguments_obj, dict):
            arguments = arguments_obj
        else:
            raise ValueError("tools/call params.arguments must be an object")

        # LINK_ONLY interception: bulk-download datasets never execute a
        # module; the hosted server returns the canonical download URL with
        # a nudge to install Sancho Fetch locally for automated ingest. This check is
        # a no-op when the requested name isn't in the dict, so non-hosted
        # sessions are unaffected.
        try:
            from sancho.mcp.hosted_allowlist import LINK_ONLY
        except Exception:
            LINK_ONLY = {}  # type: ignore[assignment]
        if name in LINK_ONLY:
            link_info = LINK_ONLY[name]
            text = (
                f"{link_info.get('description', 'Bulk-download dataset.')} "
                f"Download directly: {link_info['url']}. "
                "For automated ingest and analysis, install Sancho Fetch locally."
            )
            return {"content": [{"type": "text", "text": text}]}

        registry, _, _ = _tool_inventory(ctx)
        tool = registry.get(name)
        if tool is None:
            raise ValueError(f"Tool '{name}' is not available in this MCP session.")

        output = tool.handler(arguments)
        output_text = _json_text(output)

        # Response-size cap (hosted mode only). Enforced on the serialized
        # JSON string length in bytes. When policy.max_response_bytes is 0
        # (default for local / stdio / non-hosted paths) this check is
        # skipped entirely.
        cap = ctx.policy.max_response_bytes
        if cap and len(output_text.encode("utf-8")) > cap:
            nudge = ctx.policy.nudge_footer or (
                "Response too large for the hosted instance. "
                "Install Sancho Fetch locally for unlimited use."
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Response exceeds {cap}-byte cap. Narrow your query "
                            f"(fewer rows, tighter filters) or install Sancho Fetch locally. {nudge}"
                        ),
                    }
                ]
            }

        content: list[dict[str, Any]] = [{"type": "text", "text": output_text}]
        # Per-response nudge footer (hosted mode backstop in case the client
        # hides or truncates the initialize.instructions field).
        if ctx.policy.nudge_footer:
            content.append({"type": "text", "text": ctx.policy.nudge_footer})
        return {"content": content}
    if method == "resources/list":
        return {"resources": []}
    if method == "resources/read":
        return {"contents": []}
    raise ValueError(f"Unsupported MCP method '{method}'")
