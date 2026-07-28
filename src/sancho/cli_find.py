"""CLI for ``sancho find sources``: ranked candidate search over module metadata.

The query is split into terms; each term that appears in a module's
manifest, description, catalog.meta.json, or markdown docs adds to a score.
The CLI returns ranked candidates with the reasons. It deliberately says
"candidates" -- Sancho is not the planner. Claude/Codex still picks the
final fetch plan.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from sancho.module_packs import MODULE_PACKS, PACK_DESCRIPTIONS
from sancho.modules import discover_modules, load_template_registry
from sancho.workspace import find_workspace_root_or_none


STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "in", "on", "for", "with", "to", "by",
    "from", "all", "any", "some", "about", "data", "info", "information",
    "everything", "things", "stuff",
    # Analytic phrasing ("population over time", "deaths per county") that
    # says how the user will slice the data, not which source has it.
    "over", "under", "per", "vs", "versus", "across", "between",
}


WEIGHTS = {
    "id": 8,
    "description": 4,
    "catalog_text": 1,
    "doc_markdown": 1,
}


@dataclass
class Candidate:
    module_id: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    kind: str = "module"  # "module" | "pack" | "custom"
    member_count: int = 0
    description: str = ""
    # Geographic scope from the manifest ("us" | "global" | "eu" | ""), so an
    # agent can steer a Brazil query to a global module over a US-only one.
    coverage: str = ""


def _tokenize(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_.]+", query.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def _module_text_index(module_id: str, manifest: dict[str, Any], module_dir: Path) -> dict[str, str]:
    """Aggregate searchable text from a module directory (template or custom)."""
    description = str(manifest.get("description", "") or "")
    bits = [str(manifest.get("id", "")), str(manifest.get("description", ""))]
    fields = manifest.get("input_schema", {}) or {}
    if isinstance(fields, dict):
        bits.append(json.dumps(fields, default=str))
    catalog_text = ""
    catalog_meta = module_dir / "catalog.meta.json"
    if catalog_meta.exists():
        try:
            catalog_text = catalog_meta.read_text(encoding="utf-8")
        except Exception:
            catalog_text = ""
    schema_sample = module_dir / "schema.sample.json"
    if schema_sample.exists():
        try:
            catalog_text += "\n" + schema_sample.read_text(encoding="utf-8")
        except Exception:
            pass
    doc_text = ""
    for md_path in module_dir.rglob("*.md"):
        try:
            doc_text += "\n" + md_path.read_text(encoding="utf-8")
        except Exception:
            continue
    return {
        "id": module_id.lower(),
        "description": description.lower(),
        "catalog_text": catalog_text.lower(),
        "doc_markdown": doc_text.lower(),
    }


def _term_hit(term: str, haystack: str) -> bool:
    """Whole-word match (plus a plural 's'), so 'over' never hits 'governance'.

    Underscores and dots count as separators -- 'bank' must match the id
    'fetch.world_bank'. Very short terms fall back to substring, mirroring
    the variables scorer in cli_module_inspect.
    """
    if len(term) <= 2:
        return term in haystack
    pattern = rf"(?<![a-z0-9]){re.escape(term)}s?(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _score_module(text_index: dict[str, str], terms: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for term in terms:
        for field_name, weight in WEIGHTS.items():
            haystack = text_index.get(field_name, "")
            if _term_hit(term, haystack):
                score += weight
                reasons.append(f"{field_name}: '{term}'")
                break
    return score, reasons


def _pack_text_index(pack_id: str) -> dict[str, str]:
    description = PACK_DESCRIPTIONS.get(pack_id, "")
    return {
        "id": pack_id.lower(),
        "description": description.lower(),
        "catalog_text": "",
        "doc_markdown": "",
    }


def _rank_packs(terms: list[str]) -> list[Candidate]:
    """Rank packs by their id + description hits. Packs cluster many
    modules into one installable bundle; surfacing the right pack saves
    users from picking modules one-by-one.
    """
    packs: list[Candidate] = []
    for pack_id, member_ids in MODULE_PACKS.items():
        text_index = _pack_text_index(pack_id)
        score, reasons = _score_module(text_index, terms)
        if score <= 0:
            continue
        # Packs win ties against individual modules by a small bonus --
        # the AI should prefer "install the bundle" over "pick a module"
        # when both look equally relevant.
        packs.append(Candidate(
            module_id=pack_id,
            score=score + 1,
            reasons=reasons,
            kind="pack",
            member_count=len(member_ids),
            description=PACK_DESCRIPTIONS.get(pack_id, ""),
        ))
    packs.sort(key=lambda c: (-c.score, c.module_id))
    return packs


def find_sources(
    query: str,
    *,
    limit: int = 12,
    type_filter: str = "fetch",
    workspace_root: Path | None = None,
) -> list[Candidate]:
    """Rank candidate fetch modules AND starter packs for a natural-language query.

    Packs are ranked alongside modules; an AI agent should consider
    suggesting a pack (one install, many modules) before listing
    individual modules one at a time.

    When ``workspace_root`` is given, the workspace's ``custom/`` modules are
    ranked too (kind ``"custom"``) -- user-created sources must be as
    discoverable as bundled ones. A custom module that overrides a bundled
    id replaces the bundled entry, because it is what actually runs.
    """
    terms = _tokenize(query)
    if not terms:
        return []
    candidates: list[Candidate] = []
    candidates.extend(_rank_packs(terms))
    custom_entries: dict[str, Candidate] = {}
    if workspace_root is not None:
        for module in discover_modules(workspace_root, zone="custom", strict=False):
            if type_filter and module.type != type_filter:
                continue
            text_index = _module_text_index(module.id, module.manifest, module.module_dir)
            score, reasons = _score_module(text_index, terms)
            custom_entries[module.id] = Candidate(
                module_id=module.id,
                score=score,
                reasons=reasons,
                kind="custom",
                description=str(module.manifest.get("description", "") or ""),
                coverage=str(module.manifest.get("coverage", "") or ""),
            )
    registry = load_template_registry()
    for module in registry.values():
        if type_filter and module.type != type_filter:
            continue
        text_index = _module_text_index(module.id, module.manifest, module.template_dir)
        score, reasons = _score_module(text_index, terms)
        entry = custom_entries.get(module.id)
        if entry is not None:
            # An override often carries only the patched files, so score it
            # against the richer of the two text indexes -- a sparse override
            # must not make a relevant module undiscoverable.
            if score > entry.score:
                entry.score = score
                entry.reasons = reasons
            if not entry.description:
                entry.description = str(module.manifest.get("description", "") or "")
            if not entry.coverage:
                entry.coverage = str(module.manifest.get("coverage", "") or "")
            continue
        if score > 0:
            candidates.append(Candidate(
                module_id=module.id,
                score=score,
                reasons=reasons,
                kind="module",
                description=str(module.manifest.get("description", "") or ""),
                coverage=str(module.manifest.get("coverage", "") or ""),
            ))
    for entry in custom_entries.values():
        if entry.score > 0:
            # Same tie-bonus as packs: the user's own module wins ties
            # against a bundled one.
            entry.score += 1
            candidates.append(entry)
    candidates.sort(key=lambda c: (-c.score, c.module_id))
    return candidates[:limit]


def cmd_find_sources(args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip()
    if not query:
        print("Usage: sancho find sources \"<natural-language query>\"")
        return 1
    candidates = find_sources(
        query,
        limit=int(args.limit),
        type_filter=args.type,
        workspace_root=find_workspace_root_or_none(),
    )
    if getattr(args, "json", False):
        payload = {
            "query": query,
            "candidates": [
                {
                    "id": c.module_id,
                    "module_id": c.module_id,  # back-compat alias
                    "kind": c.kind,
                    "score": c.score,
                    "reasons": c.reasons,
                    "member_count": c.member_count,
                    "description": c.description,
                    **({"coverage": c.coverage} if c.coverage else {}),
                }
                for c in candidates
            ],
            "candidate_count": len(candidates),
            "note": (
                "These are candidates. Claude/Codex decides the final plan. "
                "When a 'pack' candidate scores well, prefer installing the "
                "pack (one `sancho add pack.<name>` command) over picking "
                "individual modules."
            ),
        }
        print(json.dumps(payload, indent=2))
        return 0
    if not candidates:
        print(f"No candidate modules matched: {query!r}")
        print("Tip: try broader terms or run 'sancho providers' for the full list.")
        return 0
    print(f"# Candidates for: {query!r}")
    print("# Packs are listed first when relevant -- install a pack with `sancho add pack.<name>`.")
    print()
    for c in candidates:
        if c.kind == "pack":
            label = f"[pack, {c.member_count} modules]"
        elif c.kind == "custom":
            label = "[custom module]"
        else:
            label = "[module]"
        if c.coverage:
            label += f" [{c.coverage}]"
        print(f"- {c.module_id:<40} {label}  score {c.score}")
        if c.description:
            print(f"    {c.description[:140]}")
        for reason in c.reasons[:5]:
            print(f"    via {reason}")
    return 0


def add_find_subcommands(subparsers: argparse._SubParsersAction) -> None:
    find = subparsers.add_parser("find", help="Search built-in and workspace custom modules for candidates")
    find_sub = find.add_subparsers(dest="find_command", required=True)

    sources = find_sub.add_parser("sources", help="Rank module candidates for a natural-language query")
    sources.add_argument("query", nargs="+", help="Free-text query, e.g. 'black population census ACS state'")
    sources.add_argument("--limit", default="12", help="Max candidates to return (default 12)")
    sources.add_argument("--type", default="fetch", help="Filter by module type (default: fetch)")
    sources.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    sources.set_defaults(func=cmd_find_sources)
