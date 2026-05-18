from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sancho.mcp.models import FamilyAliasBinding, MCPContext, ToolSpec
from sancho.mcp.quick import QUICK_PROFILE_PACKS
from sancho.modules import ModuleLocation
from sancho.runtime.executor import run_module


def _provider_from_module_id(module_id: str) -> str:
    if module_id.startswith("fetch."):
        return module_id[len("fetch.") :]
    return module_id


def _resolve_provider_module(provider: str, modules: list[ModuleLocation]) -> str:
    fetch_module_ids = sorted([module.id for module in modules if module.type == "fetch"])
    if not fetch_module_ids:
        raise ValueError("No fetch modules are installed in this MCP context.")

    token = provider.strip()
    if not token:
        raise ValueError("gov_fetch requires a non-empty provider.")

    if token in fetch_module_ids:
        return token

    direct_fetch = token if token.startswith("fetch.") else f"fetch.{token}"
    if direct_fetch in fetch_module_ids:
        return direct_fetch

    provider_map: dict[str, set[str]] = {}
    for module_id in fetch_module_ids:
        provider_path = _provider_from_module_id(module_id)
        short = provider_path.split(".", 1)[0]
        for alias in {provider_path, short}:
            provider_map.setdefault(alias, set()).add(module_id)

    matched = sorted(provider_map.get(token, set()))
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        raise ValueError(
            f"Ambiguous provider '{provider}'. Matches: {', '.join(matched)}. "
            "Use a full module ID (fetch.<provider>)."
        )

    known = ", ".join(sorted(provider_map.keys()))
    raise ValueError(f"Unknown provider '{provider}'. Known providers: {known}")


def _build_gov_catalog_payload(
    ctx: MCPContext,
    modules: list[ModuleLocation],
    aliases: list[FamilyAliasBinding],
) -> dict[str, Any]:
    installed_modules = sorted([module.id for module in modules])
    installed_fetch_modules = sorted([module.id for module in modules if module.type == "fetch"])
    providers = sorted({_provider_from_module_id(module_id) for module_id in installed_fetch_modules})

    alias_entries = [
        {
            "name": alias.name,
            "provider": alias.provider,
            "module_id": alias.module_id,
            "family_id": alias.family_id,
            "method": alias.method,
            "base": alias.base,
            "path_template": alias.path_template,
            "path_vars": list(alias.path_vars),
        }
        for alias in aliases
    ]

    return {
        "quick_mode": ctx.quick_mode,
        "workspace_root": str(ctx.workspace_root),
        "profile": ctx.quick_profile,
        "quick_targets": list(ctx.quick_targets),
        "quick_modules": list(ctx.quick_modules),
        "available_profiles": QUICK_PROFILE_PACKS,
        "installed_modules": installed_modules,
        "installed_fetch_modules": installed_fetch_modules,
        "providers": providers,
        "aliases": alias_entries,
    }


def _render_alias_path(binding: FamilyAliasBinding, arguments: dict[str, Any]) -> str:
    path = binding.path_template
    for variable in binding.path_vars:
        if variable not in arguments:
            raise ValueError(f"Alias tool '{binding.name}' requires '{variable}'")
        value = arguments[variable]
        if value is None:
            raise ValueError(f"Alias tool '{binding.name}' requires non-null '{variable}'")
        value_text = str(value)
        if not value_text.strip():
            raise ValueError(f"Alias tool '{binding.name}' requires non-empty '{variable}'")
        path = path.replace("{" + variable + "}", value_text)
    return path


@dataclass
class _ModuleToolHandler:
    workspace_root: Path
    module_id: str

    def __call__(self, arguments: dict[str, Any]) -> Any:
        result = run_module(self.workspace_root, module_id=self.module_id, input_payload=arguments)
        return result.output


@dataclass
class _GovCatalogToolHandler:
    ctx: MCPContext
    modules: list[ModuleLocation]
    aliases: list[FamilyAliasBinding]

    def __call__(self, arguments: dict[str, Any]) -> Any:
        _ = arguments
        return _build_gov_catalog_payload(self.ctx, self.modules, self.aliases)


@dataclass
class _GovFetchToolHandler:
    workspace_root: Path
    modules: list[ModuleLocation]

    def __call__(self, arguments: dict[str, Any]) -> Any:
        provider_obj = arguments.get("provider")
        if not isinstance(provider_obj, str) or not provider_obj.strip():
            raise ValueError("gov_fetch requires arguments.provider")

        payload_obj = arguments.get("payload", {})
        payload = payload_obj if payload_obj is not None else {}
        if not isinstance(payload, dict):
            raise ValueError("gov_fetch arguments.payload must be an object")

        module_id = _resolve_provider_module(provider_obj, self.modules)
        result = run_module(self.workspace_root, module_id=module_id, input_payload=payload)
        return result.output


@dataclass
class _FamilyAliasToolHandler:
    workspace_root: Path
    binding: FamilyAliasBinding

    def __call__(self, arguments: dict[str, Any]) -> Any:
        path = _render_alias_path(self.binding, arguments)
        payload: dict[str, Any] = {
            "method": self.binding.method,
            "path": path,
        }
        if self.binding.base:
            payload["base"] = self.binding.base

        params_obj = arguments.get("params")
        if params_obj is not None:
            if not isinstance(params_obj, dict):
                raise ValueError(f"Alias tool '{self.binding.name}' requires params to be an object")
            payload["params"] = params_obj

        body_obj = arguments.get("body")
        if body_obj is not None:
            if not isinstance(body_obj, dict):
                raise ValueError(f"Alias tool '{self.binding.name}' requires body to be an object")
            payload["body"] = body_obj

        result = run_module(self.workspace_root, module_id=self.binding.module_id, input_payload=payload)
        return result.output


def module_tool_spec(ctx: MCPContext, module: ModuleLocation) -> ToolSpec:
    return ToolSpec(
        name=module.id,
        description=module.manifest.get("description", module.id),
        input_schema=module.manifest.get("input_schema", {"type": "object"}),
        handler=_ModuleToolHandler(workspace_root=ctx.workspace_root, module_id=module.id),
    )


def gov_catalog_tool_spec(ctx: MCPContext, modules: list[ModuleLocation], aliases: list[FamilyAliasBinding]) -> ToolSpec:
    return ToolSpec(
        name="gov_catalog",
        description="List installed providers/modules, active quick profile, and generated gov_* aliases.",
        input_schema={"type": "object"},
        handler=_GovCatalogToolHandler(ctx=ctx, modules=modules, aliases=aliases),
    )


def gov_fetch_tool_spec(ctx: MCPContext, modules: list[ModuleLocation]) -> ToolSpec:
    return ToolSpec(
        name="gov_fetch",
        description="Run a fetch provider by provider name or module ID using the provider payload contract.",
        input_schema={
            "type": "object",
            "required": ["provider"],
            "properties": {
                "provider": {"type": "string"},
                "payload": {"type": "object"},
            },
        },
        handler=_GovFetchToolHandler(workspace_root=ctx.workspace_root, modules=modules),
    )


def family_alias_tool_spec(ctx: MCPContext, binding: FamilyAliasBinding) -> ToolSpec:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for variable in binding.path_vars:
        properties[variable] = {"type": "string"}
        required.append(variable)
    properties["params"] = {"type": "object"}
    properties["body"] = {"type": "object"}

    input_schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        input_schema["required"] = required

    description = (
        f"Alias for {binding.module_id} family '{binding.family_id}' "
        f"({binding.method} {binding.path_template})"
    )
    return ToolSpec(
        name=binding.name,
        description=description,
        input_schema=input_schema,
        handler=_FamilyAliasToolHandler(workspace_root=ctx.workspace_root, binding=binding),
    )
