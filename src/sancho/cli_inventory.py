from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import shorten
from typing import Any

from sancho.module_packs import MODULE_PACKS
from sancho.modules import TemplateModule, discover_modules, load_template_registry
from sancho.workspace import find_workspace_root_or_none


def _first_line(value: object, *, width: int = 110) -> str:
    lines = str(value or "").strip().splitlines()
    if not lines:
        return ""
    return shorten(lines[0].strip(), width=width, placeholder="...")


def _fetch_modules(registry: dict[str, TemplateModule]) -> list[TemplateModule]:
    return sorted(
        [module for module in registry.values() if module.type == "fetch"],
        key=lambda item: item.id,
    )


def _inventory_payload(workspace_root: Path | None = None) -> dict[str, Any]:
    registry = load_template_registry()

    # The user's own custom/ modules must be as visible as bundled ones,
    # or agents picking modules from inventory will never surface them.
    custom_modules: list[dict[str, Any]] = []
    if workspace_root is not None:
        for module in discover_modules(workspace_root, zone="custom", strict=False):
            custom_modules.append(
                {
                    "id": module.id,
                    "version": module.version,
                    "type": module.type,
                    "description": _first_line(module.manifest.get("description", "")),
                    "overrides_builtin": module.id in registry,
                }
            )
    custom_ids = {module["id"] for module in custom_modules}

    providers: list[dict[str, Any]] = []
    for module in _fetch_modules(registry):
        manifest = module.manifest
        providers.append(
            {
                "id": module.id,
                "version": module.version,
                "catalog_tier": manifest.get("catalog_tier", ""),
                "description": _first_line(manifest.get("description", "")),
                # Runtime resolution prefers custom/ -- flag rows whose
                # bundled metadata is not what actually runs.
                "custom_override_active": module.id in custom_ids,
                "packs": sorted(
                    pack_id
                    for pack_id, module_ids in MODULE_PACKS.items()
                    if module.id in module_ids
                ),
            }
        )

    packs = [
        {"id": pack_id, "modules": list(module_ids), "module_count": len(module_ids)}
        for pack_id, module_ids in sorted(MODULE_PACKS.items())
    ]

    return {
        "packs": packs,
        "providers": providers,
        "custom_modules": custom_modules,
        "pack_count": len(packs),
        "provider_count": len(providers),
        "custom_module_count": len(custom_modules),
    }


def _print_packs(payload: dict[str, Any]) -> None:
    print("Starter packs:")
    for pack in payload["packs"]:
        modules = ", ".join(pack["modules"])
        print(f"- {pack['id']} ({pack['module_count']} modules): {modules}")


def _print_providers(payload: dict[str, Any]) -> None:
    print("Fetch providers:")
    for provider in payload["providers"]:
        meta: list[str] = []
        if provider["catalog_tier"]:
            meta.append(str(provider["catalog_tier"]))
        if provider.get("custom_override_active"):
            meta.append("custom override active")
        meta_text = f" [{', '.join(meta)}]" if meta else ""
        description = f" - {provider['description']}" if provider["description"] else ""
        print(f"- {provider['id']}{meta_text}{description}")


def _print_custom_modules(payload: dict[str, Any]) -> None:
    print("Custom modules (yours, in this workspace):")
    for module in payload["custom_modules"]:
        override = " [overrides built-in]" if module["overrides_builtin"] else ""
        description = f" - {module['description']}" if module["description"] else ""
        print(f"- {module['id']} ({module['type']}){override}{description}")


def cmd_inventory(args: argparse.Namespace) -> int:
    payload = _inventory_payload(find_workspace_root_or_none())
    mode = getattr(args, "mode", "all")
    if getattr(args, "json", False):
        if mode == "packs":
            output: Any = {"packs": payload["packs"], "pack_count": payload["pack_count"]}
        elif mode == "providers":
            output = {
                "providers": payload["providers"],
                "provider_count": payload["provider_count"],
                "custom_modules": payload["custom_modules"],
                "custom_module_count": payload["custom_module_count"],
            }
        else:
            output = payload
        print(json.dumps(output, indent=2))
        return 0

    print("Sancho Fetch inventory")
    print(f"Built-in fetch providers: {payload['provider_count']}")
    print(f"Starter packs: {payload['pack_count']}")
    if payload["custom_modules"]:
        print(f"Custom modules in your workspace: {payload['custom_module_count']}")
    print("")

    if mode in {"all", "packs"}:
        _print_packs(payload)
        print("")

    if mode in {"all", "providers"}:
        _print_providers(payload)
        print("")
        if payload["custom_modules"]:
            _print_custom_modules(payload)
            print("")

    print("Next:")
    print("  sancho setup --install-claude-desktop")
    print("  sancho add <pack-id>")
    print("  sancho fetch sample world_bank")
    return 0


__all__ = ["cmd_inventory"]
