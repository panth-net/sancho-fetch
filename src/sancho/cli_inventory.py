from __future__ import annotations

import argparse
import json
from textwrap import shorten
from typing import Any

from sancho.module_packs import MODULE_PACKS
from sancho.modules import TemplateModule, load_template_registry


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


def _inventory_payload() -> dict[str, Any]:
    registry = load_template_registry()
    providers: list[dict[str, Any]] = []
    for module in _fetch_modules(registry):
        manifest = module.manifest
        providers.append(
            {
                "id": module.id,
                "version": module.version,
                "catalog_tier": manifest.get("catalog_tier", ""),
                "description": _first_line(manifest.get("description", "")),
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
        "pack_count": len(packs),
        "provider_count": len(providers),
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
        meta_text = f" [{', '.join(meta)}]" if meta else ""
        description = f" - {provider['description']}" if provider["description"] else ""
        print(f"- {provider['id']}{meta_text}{description}")


def cmd_inventory(args: argparse.Namespace) -> int:
    payload = _inventory_payload()
    mode = getattr(args, "mode", "all")
    if getattr(args, "json", False):
        if mode == "packs":
            output: Any = {"packs": payload["packs"], "pack_count": payload["pack_count"]}
        elif mode == "providers":
            output = {
                "providers": payload["providers"],
                "provider_count": payload["provider_count"],
            }
        else:
            output = payload
        print(json.dumps(output, indent=2))
        return 0

    print("Sancho Fetch inventory")
    print(f"Built-in fetch providers: {payload['provider_count']}")
    print(f"Starter packs: {payload['pack_count']}")
    print("")

    if mode in {"all", "packs"}:
        _print_packs(payload)
        print("")

    if mode in {"all", "providers"}:
        _print_providers(payload)
        print("")

    print("Next:")
    print("  sancho setup --install-claude-desktop")
    print("  sancho add <pack-id>")
    print("  sancho fetch sample world_bank")
    return 0


__all__ = ["cmd_inventory"]
