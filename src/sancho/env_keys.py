"""Per-provider env-var registry + the ``env_recommend`` query helper.

Single source of truth for which env vars each fetch module needs. Used
by ``sancho env open / check / recommend`` and by the MCP high-level
tools (``sancho_env_open``, ``sancho_env_recommend``).

Sign-up URLs, per-key form-field instructions, and any other context for
a key live in the user's ``.env.example`` -- the same file they're about
to open. Rather than parse comment blocks (which fragment around blank
lines and are easy to get wrong), the ``env_recommend`` payload simply
embeds the entire ``.env.example`` content. The AI assistant uses that
returned payload for sign-up URLs and field hints instead of opening the
user's real ``.env`` file. One source of truth, no drift.

Safety contract: values are never returned, printed, or stored. Only
env-var names are reported; values are checked only for non-emptiness.
The recommend helper emits names + the .env.example reference; the user
pastes values into ``.env`` themselves and Sancho re-checks presence on
the next call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sancho.constants import WORKSPACE_DIRNAME


REPO_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


MODULE_KEYS: dict[str, list[str]] = {
    "fetch.airnow": ["AIRNOW_API_KEY"],
    "fetch.atus": ["BLS_API_KEY"],
    "fetch.bea.nipa_table": ["BEA_API_KEY"],
    "fetch.bls": ["BLS_API_KEY"],
    "fetch.census.acs_profile": ["CENSUS_API_KEY"],
    "fetch.college_scorecard.schools": ["DATA_GOV_API_KEY"],
    "fetch.congress.bills": ["CONGRESS_API_KEY"],
    "fetch.dol.osha_inspections": ["DOL_API_KEY"],
    "fetch.eia.series": ["EIA_API_KEY"],
    "fetch.epa.aqs_annual": ["AQS_API_KEY", "AQS_EMAIL"],
    "fetch.fbi.crime": ["DATA_GOV_API_KEY"],
    "fetch.fda.drug_events": ["DATA_GOV_API_KEY"],
    "fetch.fec": ["DATA_GOV_API_KEY"],
    "fetch.fred.series": ["FRED_API_KEY"],
    "fetch.hud.fmr": ["HUD_API_TOKEN"],
    "fetch.noaa.cdo": ["NOAA_API_TOKEN"],
    "fetch.nrel.alt_fuel_stations": ["DATA_GOV_API_KEY"],
    "fetch.regulations.dockets": ["DATA_GOV_API_KEY"],
    "fetch.usda.fooddata_search": ["DATA_GOV_API_KEY"],
    "fetch.usda.quickstats": ["USDA_NASS_API_KEY"],
    "fetch.uspto.application": ["USPTO_API_KEY"],
    "fetch.nyc_open_data": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
    "fetch.cdc": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
    "fetch.socrata.dataset": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
    "fetch.socrata.chicago_crimes": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
    "fetch.socrata.la_crime": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
    "fetch.socrata.sf_building_permits": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
    "fetch.socrata.seattle_building_permits": ["SODA_API_KEY_ID", "SODA_API_KEY_SECRET"],
}

OPTIONAL_KEY_MODULES: set[str] = {
    "fetch.atus",
    "fetch.bls",
    "fetch.fda.drug_events",
    "fetch.nyc_open_data",
    "fetch.cdc",
    "fetch.socrata.dataset",
    "fetch.socrata.chicago_crimes",
    "fetch.socrata.la_crime",
    "fetch.socrata.sf_building_permits",
    "fetch.socrata.seattle_building_permits",
}


HIDDEN_FILE_HINTS = (
    "macOS: files starting with `.` are hidden in Finder by default. "
    "Open the Sancho Fetch workspace folder, then press Cmd+Shift+. "
    "(Command + Shift + period) to toggle hidden files. "
    "Or open the `.env` path directly from VS Code without toggling anything."
)

HIDDEN_FILE_HINTS_WINDOWS = (
    "Windows: in File Explorer, click View -> Show -> Hidden items. "
    "Or open the path directly from VS Code."
)


def provider_key_hints(provider: str) -> list[dict[str, object]]:
    token = provider.strip().lower()
    if not token:
        return []
    candidates: set[str] = set()
    if token in MODULE_KEYS:
        candidates.add(token)
    full = token if token.startswith("fetch.") else f"fetch.{token}"
    if full in MODULE_KEYS:
        candidates.add(full)
    for module_id in MODULE_KEYS:
        suffix = module_id[len("fetch."):] if module_id.startswith("fetch.") else module_id
        if suffix == token or suffix.startswith(token + "."):
            candidates.add(module_id)
    return [
        {"module_id": module_id, "env_keys": MODULE_KEYS[module_id]}
        for module_id in sorted(candidates)
    ]


def read_populated_env_keys(env_path: Path) -> set[str]:
    """Return env-var NAMES with non-empty values. Values are checked for emptiness only -- never stored."""
    return set(read_env_values(env_path))


def read_env_values(env_path: Path) -> dict[str, str]:
    """Return non-empty env values for runtime use.

    Values are intentionally only returned to trusted in-process callers.
    CLI/MCP status payloads must expose names only.
    """
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    with env_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].lstrip()
            name, value = stripped.split("=", 1)
            name = name.strip()
            value = value.strip()
            if name and value:
                values[name] = value
    return values


def project_env_path(workspace_root: Path) -> Path:
    """Return the user-facing project-level .env path for a workspace."""
    if workspace_root.name == WORKSPACE_DIRNAME:
        return workspace_root.parent / ".env"
    return workspace_root / ".env"


def workspace_env_path(workspace_root: Path) -> Path:
    return workspace_root / ".env"


def env_candidate_paths(workspace_root: Path) -> list[Path]:
    """Return env files in load order: project fallback, then workspace override."""
    project_env = project_env_path(workspace_root)
    workspace_env = workspace_env_path(workspace_root)
    if project_env.resolve() == workspace_env.resolve():
        return [workspace_env]
    return [project_env, workspace_env]


def load_env_values(workspace_root: Path) -> dict[str, str]:
    """Load Sancho env values with workspace keys overriding project fallback keys."""
    merged: dict[str, str] = {}
    for path in env_candidate_paths(workspace_root):
        merged.update(read_env_values(path))
    return merged


def resolve_env_edit_path(workspace_root: Path) -> Path:
    """Choose the most helpful .env file to open for a human.

    New users usually see the repo/project root in their editor, so prefer a
    project-level .env when it already exists or when the workspace copy has no
    provider keys yet. Existing workspaces with populated provider keys keep
    opening the workspace file.
    """
    project_env = project_env_path(workspace_root)
    workspace_env = workspace_env_path(workspace_root)
    if project_env.exists():
        return project_env
    workspace_keys = set(read_env_values(workspace_env))
    provider_keys = {key for keys in MODULE_KEYS.values() for key in keys}
    if workspace_keys & provider_keys:
        return workspace_env
    return project_env


def env_status(workspace_root: Path) -> dict[str, Any]:
    """Names-only status for all Sancho env files.

    This reports enough to diagnose split .env files without exposing values.
    """
    by_path: list[dict[str, Any]] = []
    values_by_path: dict[Path, dict[str, str]] = {}
    for path in env_candidate_paths(workspace_root):
        values = read_env_values(path)
        values_by_path[path] = values
        by_path.append({
            "path": str(path),
            "exists": path.exists(),
            "keys_present": sorted(values),
        })

    merged = load_env_values(workspace_root)
    project_env = project_env_path(workspace_root)
    workspace_env = workspace_env_path(workspace_root)
    project_values = values_by_path.get(project_env, {})
    workspace_values = values_by_path.get(workspace_env, {})
    shadowed = sorted(
        key for key in set(project_values) & set(workspace_values)
        if project_values.get(key) != workspace_values.get(key)
    )
    return {
        "env_path": str(resolve_env_edit_path(workspace_root)),
        "env_exists": resolve_env_edit_path(workspace_root).exists(),
        "workspace_env_path": str(workspace_env),
        "project_env_path": str(project_env),
        "env_paths": by_path,
        "keys_present": sorted(merged),
        "shadowed_keys": shadowed,
        "note": (
            "Project .env is used as a fallback; sancho-workspace/.env overrides "
            "matching names. Only env-var NAMES are reported. Values are never "
            "printed."
        ),
    }


def _env_example_contents(workspace_root: Path) -> tuple[Path, str | None]:
    """Find a .env.example to embed. Prefer the workspace's copy; fall back to the repo's bundled one."""
    workspace_copy = workspace_root / ".env.example"
    if workspace_copy.exists():
        try:
            return workspace_copy, workspace_copy.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    if REPO_ENV_EXAMPLE.exists():
        try:
            return REPO_ENV_EXAMPLE, REPO_ENV_EXAMPLE.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return workspace_copy, None


def env_recommend(workspace_root: Path, query: str, *, limit: int = 8) -> dict[str, Any]:
    """Combine `find_sources(query)` with per-provider key status.

    The payload is safe to send back to an AI agent: env-var names + missing
    status + the full .env.example contents (so the agent can read sign-up
    URLs and per-key form-field hints from one place). Values from .env are
    never read or returned.
    """
    from sancho.cli_find import find_sources

    query = query.strip()
    status_payload = env_status(workspace_root)
    env_path = Path(str(status_payload["env_path"]))
    env_example_path, env_example_text = _env_example_contents(workspace_root)

    if not query:
        return {
            "query": "",
            "candidates": [],
            **status_payload,
            "env_path": str(env_path),
            "env_exists": env_path.exists(),
            "env_example_path": str(env_example_path),
            "env_example_contents": env_example_text,
            "summary": {"ready": 0, "blocked_on_required_keys": 0, "no_keys_needed": 0, "total": 0},
            "next_steps": ["Provide a non-empty query like 'housing affordability'."],
        }
    from sancho.module_packs import MODULE_PACKS  # local import to avoid cycle

    candidates = find_sources(query, limit=limit)
    populated = set(status_payload["keys_present"])

    rows: list[dict[str, Any]] = []
    missing_required: set[str] = set()
    for c in candidates:
        if c.kind == "pack":
            members = MODULE_PACKS.get(c.module_id, [])
            declared = sorted({k for m in members for k in MODULE_KEYS.get(m, [])})
            required_keys = {
                k for m in members if m not in OPTIONAL_KEY_MODULES
                for k in MODULE_KEYS.get(m, [])
            }
            missing = [name for name in declared if name not in populated]
            ready = (not required_keys) or all(name in populated for name in required_keys)
            if not ready:
                missing_required.update(n for n in required_keys if n not in populated)
            rows.append({
                "id": c.module_id,
                "kind": "pack",
                "module_id": c.module_id,  # back-compat alias
                "score": c.score,
                "match_reasons": c.reasons[:3],
                "description": c.description,
                "member_count": c.member_count,
                "declared_env_keys": declared,
                "keys_optional": False,
                "missing_keys": missing,
                "ready": ready,
            })
            continue
        declared = list(MODULE_KEYS.get(c.module_id, []))
        is_optional = c.module_id in OPTIONAL_KEY_MODULES
        missing = [name for name in declared if name not in populated]
        ready = (not declared) or is_optional or (not missing)
        if not is_optional and missing:
            missing_required.update(missing)
        rows.append({
            "id": c.module_id,
            "kind": "module",
            "module_id": c.module_id,
            "score": c.score,
            "match_reasons": c.reasons[:3],
            "description": c.description,
            "declared_env_keys": declared,
            "keys_optional": is_optional,
            "missing_keys": missing,
            "ready": ready,
        })

    ready_count = sum(1 for r in rows if r["ready"])
    blocked = sum(1 for r in rows if not r["ready"])
    no_keys = sum(1 for r in rows if not r["declared_env_keys"])

    next_steps: list[str] = []
    if missing_required:
        next_steps.append(
            "DO NOT share key VALUES with me (the AI assistant). "
            "Paste each key directly into the .env file yourself."
        )
        next_steps.append(
            "Open the .env file now: run `sancho env open` "
            "(creates the file from .env.example if missing)."
        )
        next_steps.append(
            "Sign-up URLs and step-by-step instructions for every key are "
            "inside `.env.example` (embedded in this payload as "
            "`env_example_contents`). Read it once and pull the URL / "
            "field hints for each missing key."
        )
        next_steps.append("Keys to add: " + ", ".join(sorted(missing_required)) + ".")
        next_steps.append(HIDDEN_FILE_HINTS)
        next_steps.append(HIDDEN_FILE_HINTS_WINDOWS)
        next_steps.append(
            "When you're done, tell me you saved the file and I'll continue. "
            "I will re-check presence (not values) via `sancho env recommend`."
        )
    if ready_count and not blocked:
        next_steps.append(
            "All recommended providers are ready -- try `/sancho fetch` with your request."
        )
    next_steps.append(
        "Sancho NEVER reads or prints your API key VALUES. Only env-var names are inspected."
    )
    return {
        "query": query,
        **status_payload,
        "env_path": str(env_path),
        "env_exists": env_path.exists(),
        "env_example_path": str(env_example_path),
        "env_example_contents": env_example_text,
        "candidates": rows,
        "summary": {
            "ready": ready_count,
            "blocked_on_required_keys": blocked,
            "no_keys_needed": no_keys,
            "total": len(rows),
        },
        "missing_required_keys": sorted(missing_required),
        "next_steps": next_steps,
        "safety": (
            "You (the user) paste keys directly into .env. Never paste a key "
            "into the AI chat. Sancho reads only env-var NAMES, never values."
        ),
    }
