from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from sancho.constants import WORKSPACE_DIRNAME
from sancho.module_packs import MODULE_PACKS
from sancho.modules import discover_modules, install_module, load_template_registry
from sancho.workspace import initialize_workspace, resolve_workspace_root

QUICK_PROFILE_PACKS: dict[str, list[str]] = {
    "lean": ["pack.global_economic"],
    "balanced": [
        "pack.global_economic",
        "pack.us_housing",
        "pack.civic_transparency",
    ],
    "broad": [
        "pack.global_economic",
        "pack.us_housing",
        "pack.public_health",
        "pack.environment_climate",
        "pack.civic_transparency",
    ],
}
DEFAULT_QUICK_PROFILE = "broad"


@dataclass(frozen=True)
class QuickSelection:
    profile: str
    profile_targets: list[str]
    override_tokens: list[str]
    resolved_targets: list[str]
    resolved_modules: list[str]


@dataclass(frozen=True)
class QuickWorkspaceState:
    quick_home: Path
    workspace_root: Path
    selection: QuickSelection
    installed_module_ids: list[str]
    allowlisted_fetch_module_ids: list[str]


def default_quick_home() -> Path:
    return (Path.home() / ".sancho" / "mcp-quick").resolve()


def resolve_quick_home(path_arg: str | Path | None) -> Path:
    if isinstance(path_arg, Path):
        raw = path_arg
    elif isinstance(path_arg, str) and path_arg.strip():
        raw = Path(path_arg.strip())
    else:
        raw = default_quick_home()
    return raw.expanduser().resolve()


def resolve_quick_workspace_root(quick_home: str | Path | None) -> Path:
    quick_home_path = resolve_quick_home(quick_home)
    return resolve_workspace_root(quick_home_path, subdir=WORKSPACE_DIRNAME)


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _parse_modules_csv(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [token.strip() for token in raw.split(",") if token.strip()]


def _provider_short_map(module_ids: set[str]) -> dict[str, set[str]]:
    provider_map: dict[str, set[str]] = {}
    for module_id in sorted(module_ids):
        if not module_id.startswith("fetch."):
            continue
        provider_path = module_id[len("fetch.") :]
        short = provider_path.split(".", 1)[0]
        for token in {provider_path, short}:
            provider_map.setdefault(token, set()).add(module_id)
    return provider_map


def _suggestions(token: str, choices: list[str]) -> list[str]:
    return difflib.get_close_matches(token, choices, n=4, cutoff=0.45)


def _unknown_token_error(token: str, choices: list[str]) -> ValueError:
    suggestions = _suggestions(token, choices)
    suggestion_text = ""
    if suggestions:
        suggestion_text = f" Suggestions: {', '.join(suggestions)}."
    return ValueError(
        "Unknown --modules token "
        f"'{token}'. Use full IDs (for example 'fetch.world_bank', 'pack.us_housing') "
        "or provider short names (for example 'world_bank', 'bls', 'cdc')."
        f"{suggestion_text}"
    )


def _resolve_override_token(
    token: str,
    *,
    module_ids: set[str],
    pack_ids: set[str],
    provider_map: dict[str, set[str]],
) -> str:
    if token in module_ids or token in pack_ids:
        return token

    if token.startswith("fetch.") or token.startswith("pack."):
        choices = sorted(module_ids | pack_ids)
        raise _unknown_token_error(token, choices)

    direct_fetch = f"fetch.{token}"
    if direct_fetch in module_ids:
        return direct_fetch

    provider_matches = sorted(provider_map.get(token, set()))
    if len(provider_matches) == 1:
        return provider_matches[0]
    if len(provider_matches) > 1:
        raise ValueError(
            f"Ambiguous --modules token '{token}'. Matches: {', '.join(provider_matches)}. "
            "Use a full module ID."
        )

    token_choices = sorted(set(provider_map.keys()) | module_ids | pack_ids)
    raise _unknown_token_error(token, token_choices)


def resolve_quick_selection(profile: str, modules_csv: str | None) -> QuickSelection:
    normalized_profile = profile.strip().lower()
    if normalized_profile not in QUICK_PROFILE_PACKS:
        known = ", ".join(sorted(QUICK_PROFILE_PACKS))
        raise ValueError(f"Unsupported quick profile '{profile}'. Supported: {known}")

    profile_targets = list(QUICK_PROFILE_PACKS[normalized_profile])
    override_tokens = _parse_modules_csv(modules_csv)
    template_registry = load_template_registry()
    module_ids = set(template_registry.keys())
    pack_ids = set(MODULE_PACKS.keys())
    provider_map = _provider_short_map(module_ids)

    resolved_overrides: list[str] = []
    for token in override_tokens:
        resolved_overrides.append(
            _resolve_override_token(
                token,
                module_ids=module_ids,
                pack_ids=pack_ids,
                provider_map=provider_map,
            )
        )

    resolved_targets = _dedupe_preserve(profile_targets + resolved_overrides)
    expanded_modules: list[str] = []
    for target in resolved_targets:
        expanded_modules.extend(MODULE_PACKS.get(target, [target]))
    resolved_modules = _dedupe_preserve(expanded_modules)

    unknown_modules = [module_id for module_id in resolved_modules if module_id not in module_ids]
    if unknown_modules:
        raise ValueError(
            "Quick mode target resolution referenced modules that are not in the template registry: "
            f"{', '.join(sorted(unknown_modules))}"
        )

    disallowed_modules = [module_id for module_id in resolved_modules if not module_id.startswith("fetch.")]
    if disallowed_modules:
        raise ValueError(
            "Quick mode supports fetch modules only. Remove non-fetch targets: "
            f"{', '.join(sorted(disallowed_modules))}"
        )

    return QuickSelection(
        profile=normalized_profile,
        profile_targets=profile_targets,
        override_tokens=override_tokens,
        resolved_targets=resolved_targets,
        resolved_modules=resolved_modules,
    )


def ensure_quick_workspace(
    *,
    profile: str = DEFAULT_QUICK_PROFILE,
    modules_csv: str | None = None,
    quick_home: str | Path | None = None,
    sync: bool = False,
    install_targets: bool = True,
    channel: str = "stable",
) -> QuickWorkspaceState:
    quick_home_path = resolve_quick_home(quick_home)
    workspace_root = initialize_workspace(base_path=quick_home_path, subdir=WORKSPACE_DIRNAME, mode="coder")
    selection = resolve_quick_selection(profile=profile, modules_csv=modules_csv)

    installed_source = {module.id for module in discover_modules(workspace_root, zone="source")}
    if not install_targets:
        install_order: list[str] = []
    elif sync:
        install_order = list(selection.resolved_modules)
    else:
        install_order = [module_id for module_id in selection.resolved_modules if module_id not in installed_source]

    for module_id in install_order:
        install_module(workspace_root, module_id=module_id, channel=channel)

    installed_fetch = sorted(
        {
            module.id
            for module in discover_modules(workspace_root, zone="source")
            if str(module.manifest.get("type", "")).strip() == "fetch"
        }
    )

    return QuickWorkspaceState(
        quick_home=quick_home_path,
        workspace_root=workspace_root,
        selection=selection,
        installed_module_ids=install_order,
        allowlisted_fetch_module_ids=installed_fetch,
    )
