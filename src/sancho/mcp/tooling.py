from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

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
    mcp_tool_name,
    module_tool_spec,
    unique_tool_name,
)
from sancho.modules import ModuleLocation, discover_modules
from sancho.provider_kits import load_provider_catalog

_ALIAS_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")
_ALIAS_SAFE_RE = re.compile(r"[^a-z0-9]+")

# Published MCP protocol versions sancho speaks. Legacy versions negotiate a
# session via the initialize handshake; the modern 2026-07-28 revision is
# stateless (per-request _meta, server/discover instead of initialize).
# Sancho is a dual-era server per the 2026-07-28 versioning spec: an
# initialize request selects legacy semantics, everything else is served
# statelessly, and both eras run concurrently on the same process.
# Source: https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
_LEGACY_MCP_PROTOCOL_VERSIONS = (
    "2024-10-07",
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
_MODERN_MCP_PROTOCOL_VERSIONS = ("2026-07-28",)
_SUPPORTED_MCP_PROTOCOL_VERSIONS = (
    _LEGACY_MCP_PROTOCOL_VERSIONS + _MODERN_MCP_PROTOCOL_VERSIONS
)
_LATEST_LEGACY_MCP_PROTOCOL_VERSION = _LEGACY_MCP_PROTOCOL_VERSIONS[-1]

_META_PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
_META_SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"

# Freshness hints (CacheableResult, required on list results since 2026-07-28).
# The tool list only changes when modules are installed or removed, so a short
# TTL is safe; discovery data is fixed for the life of the process.
_LIST_TTL_MS = 300_000
_DISCOVER_TTL_MS = 3_600_000


class MCPProtocolError(ValueError):
    """JSON-RPC error carrying a specific error code."""

    code = -32000
    data: dict[str, Any] | None = None


class MCPMethodNotFound(MCPProtocolError):
    code = -32601


class MCPInvalidParams(MCPProtocolError):
    code = -32602


class MCPHeaderMismatch(MCPProtocolError):
    code = -32020


class MCPUnsupportedProtocolVersion(MCPProtocolError):
    code = -32022

    def __init__(self, requested: str, *, supported: tuple[str, ...] | None = None) -> None:
        super().__init__("Unsupported protocol version")
        self.data = {
            "supported": list(reversed(supported or _SUPPORTED_MCP_PROTOCOL_VERSIONS)),
            "requested": requested,
        }


def jsonrpc_error(exc: Exception) -> dict[str, Any]:
    """Map an exception to a JSON-RPC error object with the right code."""
    error: dict[str, Any] = {
        "code": exc.code if isinstance(exc, MCPProtocolError) else -32000,
        "message": str(exc),
    }
    if isinstance(exc, MCPProtocolError) and exc.data:
        error["data"] = exc.data
    return error


def _negotiate_protocol_version(requested: Any) -> str:
    """Echo the client's version if supported, else return our latest legacy.

    Only handshake-era clients call initialize, so the fallback must be a
    version whose lifecycle includes initialize. Returning a version the
    client doesn't recognize (e.g. a future or made-up date) causes clients
    such as Claude Desktop to disconnect immediately after the initialize
    response.
    """
    if isinstance(requested, str) and requested in _LEGACY_MCP_PROTOCOL_VERSIONS:
        return requested
    return _LATEST_LEGACY_MCP_PROTOCOL_VERSION


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
            # Cap to the MCP name limit here, at the mint site, so binding.name
            # is the final published name and the gov_catalog payload (which
            # echoes alias.name) stays consistent with tools/list.
            base_name = mcp_tool_name(f"gov_{provider_slug}__{family_slug}")
            alias_name = unique_tool_name(base_name, used_names)
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


def _register_tool(
    registry: dict[str, ToolSpec],
    used: set[str],
    spec: ToolSpec,
    *,
    raw: str | None = None,
) -> str:
    """Add a spec to the registry under a unique, pattern-conformant name.

    ``mcp_tool_name`` is idempotent on already-safe names (gov_*, sancho_*,
    family aliases), so they pass through unchanged; module ids get their dots
    replaced. When ``raw`` (the original dotted module id) differs from the
    safe name it is registered as a back-compat dispatch alias. A raw key always
    contains a sanitized-away char, so it can never clobber a (dot-free)
    canonical key, and it is filtered out of tools/list by the dedupe in
    ``_tools_payload``.

    Returns the final published name (after collision suffixing) so callers can
    record the authoritative id/binding -> name mapping.
    """
    name = unique_tool_name(mcp_tool_name(spec.name), used)
    spec.name = name
    used.add(name)
    registry[name] = spec
    if raw and raw != name:
        registry.setdefault(raw, spec)
    return name


def _tool_inventory(ctx: MCPContext) -> tuple[dict[str, ToolSpec], list[ModuleLocation], list[FamilyAliasBinding]]:
    modules = _discover_exposed_modules(ctx)
    registry: dict[str, ToolSpec] = {}
    used: set[str] = set()
    # Authoritative module id -> final published tool name. Shared by reference
    # with the gov_catalog handler so the catalog advertises exactly what
    # tools/list exposes (post de-dup), instead of recomputing names.
    name_by_module_id: dict[str, str] = {}

    aliases: list[FamilyAliasBinding] = []
    if ctx.quick_mode:
        try:
            cache_root = resolve_cache_dir(load_workspace_config(ctx.workspace_root))
        except Exception:
            cache_root = None
        aliases = _build_family_alias_bindings(modules, cache_root=cache_root)

    # Reserve the fixed core/high-level tool names FIRST, before any module or
    # alias. Otherwise a module id (or custom module) that normalizes onto a
    # reserved name, e.g. "gov.catalog" -> "gov_catalog", would claim it and
    # silently push the real tool to "gov_catalog_2", so tools/call gov_catalog
    # would run the module. Reserving first makes the core tool win and any
    # colliding module/alias take the suffix instead.
    # build_high_level_tools returns [] when ctx.policy.stateless is True
    # (hosted MCP) because those endpoints cannot access the user's workspace.
    core_specs: list[ToolSpec] = list(build_high_level_tools(ctx))
    if ctx.quick_mode:
        core_specs.append(gov_catalog_tool_spec(ctx, modules, aliases, name_by_module_id))
        core_specs.append(gov_fetch_tool_spec(ctx, modules))
    for spec in core_specs:
        _register_tool(registry, used, spec)

    # Module tools. Record the final (possibly suffixed) published name.
    for module in modules:
        final = _register_tool(registry, used, module_tool_spec(ctx, module), raw=module.id)
        name_by_module_id[module.id] = final

    # Family aliases. Write the final published name back into the binding so the
    # gov_catalog payload (which echoes binding.name) stays consistent with
    # tools/list even when a collision forces a suffix here.
    for alias in aliases:
        alias.name = _register_tool(registry, used, family_alias_tool_spec(ctx, alias))

    return registry, modules, aliases


def _tools_payload(ctx: MCPContext) -> dict[str, Any]:
    registry, _, _ = _tool_inventory(ctx)
    tools: list[dict[str, Any]] = []
    # Publish each spec once under its canonical name. Back-compat raw (dotted)
    # keys point at a spec already published under its safe name, so dedupe by
    # tool.name to keep them out of tools/list.
    seen: set[str] = set()
    for key in sorted(registry):
        tool = registry[key]
        if tool.name in seen:
            continue
        seen.add(tool.name)
        entry: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }
        if tool.title:
            entry["title"] = tool.title
        if tool.annotations:
            entry["annotations"] = tool.annotations
        tools.append(entry)
    return {"tools": tools}


def _cache_fields(ctx: MCPContext, ttl_ms: int) -> dict[str, Any]:
    # cacheScope controls whether shared intermediaries may cache the result:
    # the hosted server returns identical payloads for everyone; a local
    # workspace server is single-user.
    return {"ttlMs": ttl_ms, "cacheScope": "public" if ctx.policy.stateless else "private"}


def _modern_protocol_version(params: dict[str, Any]) -> str | None:
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None
    requested = meta.get(_META_PROTOCOL_VERSION_KEY)
    if requested is None:
        return None
    if not isinstance(requested, str) or requested not in _MODERN_MCP_PROTOCOL_VERSIONS:
        raise MCPUnsupportedProtocolVersion(
            str(requested), supported=_MODERN_MCP_PROTOCOL_VERSIONS
        )
    client_info = meta.get("io.modelcontextprotocol/clientInfo")
    if client_info is not None and not isinstance(client_info, dict):
        raise MCPInvalidParams("modern _meta clientInfo must be an object")
    capabilities = meta.get("io.modelcontextprotocol/clientCapabilities")
    if capabilities is not None and not isinstance(capabilities, dict):
        raise MCPInvalidParams("modern _meta clientCapabilities must be an object")
    return requested


def _finalize_modern_result(result: dict[str, Any]) -> dict[str, Any]:
    """Stamp fields that exist only in the stateless 2026 protocol era."""
    result.setdefault("resultType", "complete")
    meta = result.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta.setdefault(_META_SERVER_INFO_KEY, {"name": "sancho-mcp", "version": __version__})
    return result


ProtocolEra = Literal["legacy", "modern"]


def _request_era(
    method: str,
    params: dict[str, Any],
    *,
    protocol_era: ProtocolEra | None = None,
) -> ProtocolEra:
    """Resolve the wire codec without allowing one era to leak into another."""
    if method == "initialize":
        return "legacy"
    if method == "server/discover":
        return "modern"
    modern_version = _modern_protocol_version(params)
    if protocol_era == "modern" and modern_version is None:
        raise MCPInvalidParams(
            "modern requests require _meta.io.modelcontextprotocol/protocolVersion"
        )
    if modern_version is not None:
        return "modern"
    return protocol_era or "legacy"


def _handle_method(
    ctx: MCPContext,
    method: str,
    params: Any,
    *,
    protocol_era: ProtocolEra | None = None,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise MCPInvalidParams("params must be a JSON object when present")
    era = _request_era(method, params, protocol_era=protocol_era)
    result = _dispatch_method(ctx, method, params, protocol_era=era)
    return _finalize_modern_result(result) if era == "modern" else result


def _dispatch_method(
    ctx: MCPContext,
    method: str,
    params: dict[str, Any],
    *,
    protocol_era: ProtocolEra,
) -> dict[str, Any]:
    if method == "initialize":
        # Legacy-era handshake, kept for handshake-era clients (dual-era server).
        result: dict[str, Any] = {
            "protocolVersion": _negotiate_protocol_version(params.get("protocolVersion")),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sancho-mcp", "version": __version__},
        }
        if ctx.policy.instructions:
            result["instructions"] = ctx.policy.instructions
        return result
    if method == "server/discover":
        result = {
            "supportedVersions": list(reversed(_MODERN_MCP_PROTOCOL_VERSIONS)),
            "capabilities": {"tools": {}},
            **_cache_fields(ctx, _DISCOVER_TTL_MS),
        }
        if ctx.policy.instructions:
            result["instructions"] = ctx.policy.instructions
        return result
    if method == "ping":
        # Removed in 2026-07-28; legacy clients still send it.
        if protocol_era == "modern":
            raise MCPMethodNotFound("Unsupported MCP method 'ping'")
        return {}
    if method == "tools/list":
        result = _tools_payload(ctx)
        if protocol_era == "modern":
            result.update(_cache_fields(ctx, _LIST_TTL_MS))
        return result
    if method == "tools/call":
        name = params.get("name")
        arguments_obj = params.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            raise MCPInvalidParams("tools/call requires params.name")
        if arguments_obj is None:
            arguments = {}
        elif isinstance(arguments_obj, dict):
            arguments = arguments_obj
        else:
            raise MCPInvalidParams("tools/call params.arguments must be an object")

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
            raise MCPInvalidParams(f"Tool '{name}' is not available in this MCP session.")

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
        # hides or truncates the instructions field).
        if ctx.policy.nudge_footer:
            content.append({"type": "text", "text": ctx.policy.nudge_footer})
        result = {"content": content}
        # structuredContent duplicates the serialized payload on the wire;
        # skip it when a response byte cap is active (hosted) so the cap
        # keeps bounding what actually ships.
        if isinstance(output, dict) and not cap:
            result["structuredContent"] = output
        return result
    raise MCPMethodNotFound(f"Unsupported MCP method '{method}'")
