"""CLI for ``sancho module show / files / status / docs / variables``."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from sancho.modules import (
    discover_module_map,
    load_template_registry,
    slugify_module_id,
)
from sancho.run_log import LOGS_DIRNAME, RUNS_LOG
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


def _last_run_for(workspace_root: Path, module_id: str) -> dict[str, Any] | None:
    runs_log = workspace_root / LOGS_DIRNAME / RUNS_LOG
    if not runs_log.exists():
        return None
    last_success: dict[str, Any] | None = None
    last_failure: dict[str, Any] | None = None
    for line in runs_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("module_id") != module_id:
            continue
        if event.get("event_type") != "run_finished":
            continue
        if event.get("status") in {"success_with_data", "success_empty"}:
            last_success = event
        else:
            last_failure = event
    return {"last_success": last_success, "last_failure": last_failure}


def _module_payload(workspace_root: Path, module_id: str) -> dict[str, Any] | None:
    source = discover_module_map(workspace_root, zone="source").get(module_id)
    custom = discover_module_map(workspace_root, zone="custom").get(module_id)
    template = load_template_registry().get(module_id)
    if source is None and custom is None and template is None:
        return None

    active = custom or source
    override_active = custom is not None
    manifest = active.manifest if active else (template.manifest if template else {})

    payload: dict[str, Any] = {
        "module_id": module_id,
        "type": manifest.get("type", ""),
        "version": str(manifest.get("version", "")),
        "entrypoint": manifest.get("entrypoint", ""),
        "description": manifest.get("description", ""),
        "input_schema": manifest.get("input_schema", {}),
        "output_schema": manifest.get("output_schema", {}),
        "managed_paths": list(manifest.get("managed_paths") or []),
        "catalog_tier": manifest.get("catalog_tier", ""),
        "custom_override_active": override_active,
        "source_path": str(source.module_dir) if source else None,
        "custom_path": str(custom.module_dir) if custom else None,
        "template_path": str(template.template_dir) if template else None,
    }
    runs = _last_run_for(workspace_root, module_id)
    if runs is not None:
        payload["last_run"] = runs
    return payload


def cmd_module_show(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    payload = _module_payload(workspace_root, args.module_id)
    if payload is None:
        print(f"Module not found: {args.module_id}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"# {payload['module_id']}")
    print(f"- type:        {payload['type']}")
    print(f"- version:     {payload['version']}")
    print(f"- entrypoint:  {payload['entrypoint']}")
    if payload["description"]:
        print(f"- description: {payload['description']}")
    if payload["catalog_tier"]:
        print(f"- catalog_tier: {payload['catalog_tier']}")
    print(f"- custom_override_active: {payload['custom_override_active']}")
    if payload["source_path"]:
        print(f"- source_path: {payload['source_path']}")
    if payload["custom_path"]:
        print(f"- custom_path: {payload['custom_path']}")
    if payload["template_path"]:
        print(f"- template_path: {payload['template_path']}")
    if payload.get("last_run"):
        runs = payload["last_run"]
        if runs.get("last_success"):
            print(f"- last_success: {runs['last_success'].get('finished_at')} (run_id={runs['last_success'].get('run_id')})")
        if runs.get("last_failure"):
            print(f"- last_failure: {runs['last_failure'].get('finished_at')} (run_id={runs['last_failure'].get('run_id')})")
    return 0


def cmd_module_files(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    source = discover_module_map(workspace_root, zone="source").get(args.module_id)
    custom = discover_module_map(workspace_root, zone="custom").get(args.module_id)
    active = custom or source
    if active is None:
        print(f"Module not installed: {args.module_id}", file=sys.stderr)
        return 1
    files = sorted(
        str(p.relative_to(active.module_dir).as_posix())
        for p in active.module_dir.rglob("*") if p.is_file()
    )
    payload = {
        "module_id": args.module_id,
        "module_dir": str(active.module_dir),
        "zone": active.zone,
        "files": files,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0
    print(f"# {args.module_id} files ({active.zone} @ {active.module_dir})")
    for f in files:
        print(f"  {f}")
    return 0


def cmd_module_status(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    payload = _module_payload(workspace_root, args.module_id)
    if payload is None:
        print(f"Module not found: {args.module_id}", file=sys.stderr)
        return 1
    status = {
        "module_id": args.module_id,
        "installed": bool(payload["source_path"]) or bool(payload["custom_path"]),
        "in_source": bool(payload["source_path"]),
        "in_custom": bool(payload["custom_path"]),
        "custom_override_active": payload["custom_override_active"],
        "version": payload["version"],
        "last_run": payload.get("last_run"),
    }
    if getattr(args, "json", False):
        print(json.dumps(status, indent=2, default=str))
        return 0
    print(f"# {status['module_id']} status")
    print(f"- installed: {status['installed']}")
    print(f"- in_source: {status['in_source']}")
    print(f"- in_custom: {status['in_custom']}")
    print(f"- custom_override_active: {status['custom_override_active']}")
    print(f"- version: {status['version']}")
    if status["last_run"]:
        if status["last_run"].get("last_success"):
            print(f"- last_success_at: {status['last_run']['last_success'].get('finished_at')}")
        if status["last_run"].get("last_failure"):
            print(f"- last_failure_at: {status['last_run']['last_failure'].get('finished_at')}")
    return 0


def cmd_module_docs(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    source = discover_module_map(workspace_root, zone="source").get(args.module_id)
    custom = discover_module_map(workspace_root, zone="custom").get(args.module_id)
    active = custom or source
    template = load_template_registry().get(args.module_id)
    search_dirs: list[Path] = []
    if active is not None:
        search_dirs.append(active.module_dir)
    if template is not None:
        search_dirs.append(template.template_dir)
    if not search_dirs:
        print(f"Module not found: {args.module_id}", file=sys.stderr)
        return 1
    docs: dict[str, list[str]] = {}
    for d in search_dirs:
        markdowns = sorted(str(p.relative_to(d).as_posix()) for p in d.rglob("*.md"))
        meta = d / "catalog.meta.json"
        sample = d / "schema.sample.json"
        manifest = d / "module.yaml"
        section = {
            "markdowns": markdowns,
            "catalog_meta": str(meta) if meta.exists() else None,
            "schema_sample": str(sample) if sample.exists() else None,
            "module_yaml": str(manifest) if manifest.exists() else None,
        }
        docs[str(d)] = section
    if getattr(args, "json", False):
        print(json.dumps({"module_id": args.module_id, "docs": docs}, indent=2))
        return 0
    print(f"# {args.module_id} docs")
    for d, section in docs.items():
        print(f"\n## {d}")
        for k, v in section.items():
            if isinstance(v, list):
                print(f"- {k}: {v or '(none)'}")
            else:
                print(f"- {k}: {v or '(missing)'}")
    return 0


def _resolve_module_dir(workspace_root: Path, module_id: str) -> tuple[Path | None, str | None]:
    """Return the best available directory for a module (custom > source > template)."""
    custom = discover_module_map(workspace_root, zone="custom").get(module_id)
    if custom is not None:
        return custom.module_dir, "custom"
    source = discover_module_map(workspace_root, zone="source").get(module_id)
    if source is not None:
        return source.module_dir, "source"
    template = load_template_registry().get(module_id)
    if template is not None:
        return template.template_dir, "template"
    return None, None


def _load_catalog(module_dir: Path) -> dict[str, Any] | None:
    catalog_path = module_dir / "catalog.json"
    if not catalog_path.exists():
        return None
    try:
        return json.loads(catalog_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _dataset_short_id(identifier: str | None) -> str:
    """Census identifiers look like https://api.census.gov/data/id/ACSDP5Y2023."""
    if not identifier:
        return ""
    return identifier.rstrip("/").rsplit("/", 1)[-1]


def _module_seed_tokens(module_id: str) -> list[str]:
    """Search tokens from the module id's last segment ('acs_profile' -> ['acs', 'profile'])."""
    tail = module_id.rsplit(".", 1)[-1]
    return [token for token in tail.split("_") if token]


def _datasets_matching_tokens(
    datasets: list[dict[str, Any]], tokens: list[str]
) -> list[dict[str, Any]]:
    matched = []
    for dataset in datasets:
        haystack = f"{dataset.get('identifier') or ''} {dataset.get('title') or ''}".lower()
        if all(token in haystack for token in tokens):
            matched.append(dataset)
    return matched


def _dataset_recency_key(dataset: dict[str, Any]) -> str:
    return str(dataset.get("temporal") or "")


def _match_datasets(catalog: dict[str, Any], query: str) -> list[dict[str, Any]]:
    datasets = catalog.get("datasets") or []
    if not query:
        return list(datasets)
    q = query.strip().lower()
    exact = [
        d for d in datasets
        if _dataset_short_id(d.get("identifier")).lower() == q
    ]
    if exact:
        return exact
    return [
        d for d in datasets
        if q in (d.get("identifier") or "").lower() or q in (d.get("title") or "").lower()
    ]


def _variables_url_for(dataset: dict[str, Any]) -> str | None:
    """Derive the variable-dictionary URL for a DCAT dataset.

    Prefer an explicit ``describedBy`` JSON link; otherwise fall back to the
    Census-style convention ``<accessURL>/variables.json`` for API endpoints.
    """
    described_by = dataset.get("describedBy")
    if isinstance(described_by, str) and described_by.lower().endswith(".json"):
        return described_by
    for dist in dataset.get("distribution") or []:
        if not isinstance(dist, dict):
            continue
        access = dist.get("accessURL")
        is_api = (dist.get("format") or "").upper() == "API" or (
            isinstance(access, str) and "api." in access
        )
        if isinstance(access, str) and is_api:
            return access.rstrip("/") + "/variables.json"
    return None


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "dataset"


def _load_variable_dictionary(
    url: str, cache_path: Path, *, refresh: bool
) -> tuple[dict[str, Any], str]:
    """Return (parsed variables.json, source) where source is 'cache' or 'live'."""
    if cache_path.exists() and not refresh:
        try:
            return json.loads(cache_path.read_text(encoding="utf-8")), "cache"
        except (json.JSONDecodeError, OSError):
            pass  # fall through to a live fetch
    from sancho.runtime.net import get_json

    data = get_json(url, timeout=60)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data, "live"


def _flatten_variables(data: dict[str, Any]) -> list[dict[str, Any]]:
    variables = data.get("variables") if isinstance(data, dict) else None
    if not isinstance(variables, dict):
        return []
    rows: list[dict[str, Any]] = []
    for code, meta in variables.items():
        if code in {"for", "in", "ucgid"}:  # geography predicates, not data fields
            continue
        meta = meta if isinstance(meta, dict) else {}
        rows.append(
            {
                "code": code,
                "label": (meta.get("label") or "").replace("!!", " > "),
                "concept": meta.get("concept") or "",
                "group": meta.get("group") or "",
                "predicateType": meta.get("predicateType") or "",
            }
        )
    return rows


def _term_hit(term: str, text: str) -> bool:
    """Whole-word match so 'age' does not match 'percentage' / 'average'.

    Falls back to substring for short/embedded code tokens (<=2 chars) where word
    boundaries are unhelpful.
    """
    if len(term) <= 2:
        return term in text
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def _score_variable_rows(
    rows: list[dict[str, Any]], terms: list[str], *, require_all: bool
) -> list[tuple[tuple[int, int, int], dict[str, Any]]]:
    """Score rows by term hits for ranking. ``require_all`` keeps only rows that
    match every term (precision); False keeps any partial match (recall fallback)."""
    res: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for r in rows:
        label, concept, codel = r["label"].lower(), r["concept"].lower(), r["code"].lower()
        hits = sum(1 for t in terms if _term_hit(t, label) or _term_hit(t, concept) or t in codel)
        if (require_all and hits < len(terms)) or hits == 0:
            continue
        label_hits = sum(_term_hit(t, label) for t in terms)
        # Rank: most terms matched, then most matched in the LABEL, then the
        # shortest (most specific) label.
        res.append(((hits, label_hits, -len(label)), r))
    return res


def _filter_variables(
    rows: list[dict[str, Any]], *, search: str | None, code: str | None
) -> list[dict[str, Any]]:
    out = rows
    if code:
        c = code.strip().lower()
        out = [r for r in out if r["code"].lower() == c or r["code"].lower().startswith(c)]
    if not search:
        return sorted(out, key=lambda r: r["code"])

    terms = [t for t in search.lower().split() if t]
    scored = _score_variable_rows(out, terms, require_all=True)
    if not scored and len(terms) > 1:
        # No row matched every term -> fall back to best partial match so the
        # agent gets relevant candidates instead of an empty result to guess from.
        scored = _score_variable_rows(out, terms, require_all=False)
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]


_CODEBOOK_META_KEYS = {
    "provider", "schema_version", "generated_at", "families", "conformsTo",
    "describedBy", "stats", "discovery", "datasets",
}


def _visit_code_lists(
    name: str, value: Any, depth: int, sections: list[tuple[str, list[Any]]]
) -> None:
    """Recursively collect non-empty lists as (dotted_name, items) sections,
    unwrapping the `{value_count, values:[...]}` shape (usda) to keep names clean."""
    if depth > 3:
        return
    if isinstance(value, list) and value:
        sections.append((name, value))
        return
    if isinstance(value, dict):
        inner = value.get("values")
        if isinstance(inner, list) and inner:
            sections.append((name, inner))
            return
        for sub_key, sub_value in value.items():
            _visit_code_lists(f"{name}.{sub_key}" if name else str(sub_key), sub_value, depth + 1, sections)


def _walk_codebook_sections(catalog: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    """Find code-list sections bundled in a provider-specific catalog.

    Non-Census catalogs ship their codebook directly, but in heterogeneous shapes:
    a top-level list (nhtsa `vehicle_variables`), a dict of lists (bls
    `indices.surveys`, world_bank `indices.indicators`), or a dict of
    `{value_count, values:[...]}` entries (usda `parameters.commodity_desc`).
    Recurse (bounded) and collect every non-empty list as a (dotted_name, items)
    section, unwrapping the `{values:[...]}` pattern to keep names readable.
    """
    sections: list[tuple[str, list[Any]]] = []
    for key, value in catalog.items():
        if key in _CODEBOOK_META_KEYS:
            continue
        _visit_code_lists(key, value, 0, sections)
    return sections


def _match_codebook_items(items: list[Any], terms: list[str], *, require_all: bool) -> list[Any]:
    """Filter bundled-codebook items by term hits (whole-word) over their JSON text."""
    hit = []
    for it in items:
        text = json.dumps(it, default=str).lower()
        n = sum(1 for t in terms if _term_hit(t, text))
        if (n == len(terms)) if require_all else (n > 0):
            hit.append(it)
    return hit


def _emit_bundled_codebook(args: argparse.Namespace, catalog: dict[str, Any], zone: str | None) -> int:
    """Surface a provider's bundled codebook (catalogs without a `datasets` list)."""
    sections = _walk_codebook_sections(catalog)
    terms = [t for t in (args.search or "").lower().split() if t]

    out_sections: list[dict[str, Any]] = []
    for name, items in sections:
        if not terms:
            matched = items
        else:
            matched = _match_codebook_items(items, terms, require_all=True)
            if not matched and len(terms) > 1:
                matched = _match_codebook_items(items, terms, require_all=False)  # partial fallback
        out_sections.append({
            "section": name,
            "count": len(items),
            "shown": min(len(matched), args.limit),
            "items": matched[: args.limit],
        })
    # When searching, drop sections with no hits so the signal is clean.
    if terms:
        out_sections = [s for s in out_sections if s["items"]]
    payload = {
        "module_id": args.module_id,
        "zone": zone,
        "mode": "bundled_codebook",
        "search": args.search or None,
        "sections": out_sections,
        "hint": (
            "This module's codebook ships inside its catalog (no live fetch needed). "
            "Use these code/label values directly; do not guess."
        ),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if not out_sections:
        print(f"# {args.module_id}: no codebook entries match '{args.search or ''}'")
        return 0
    print(f"# {args.module_id} bundled codebook ({len(out_sections)} section(s))")
    for s in out_sections:
        print(f"  {s['section']}: {s['count']} entr(ies); showing {s['shown']}")
    return 0


def _load_manifest(module_dir: Path) -> dict[str, Any]:
    path = module_dir / "module.yaml"
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def _parse_worldbank_indicators(data: Any) -> list[dict[str, Any]]:
    """World Bank indicator endpoint: [meta, [ {id, name, source, sourceNote}, ... ]]."""
    rows: list[dict[str, Any]] = []
    items = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        rows.append({
            "code": item.get("id") or "",
            "label": item.get("name") or "",
            "concept": (source.get("value") or "") if isinstance(source, dict) else "",
            "group": "",
            "predicateType": "",
        })
    return rows


_CODEBOOK_PARSERS = {
    "census_variables": _flatten_variables,
    "worldbank_indicators": _parse_worldbank_indicators,
}


def _emit_variable_rows(
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    *,
    zone: str | None,
    source: str,
    url: str,
    dataset: str | None = None,
    dataset_title: str | None = None,
) -> int:
    """Filter, rank, and print a flat list of code/label rows (shared output path)."""
    filtered = _filter_variables(rows, search=args.search, code=args.code)
    shown = filtered[: args.limit]
    payload = {
        "module_id": args.module_id,
        "zone": zone,
        "mode": "variables",
        "dataset": dataset,
        "dataset_title": dataset_title,
        "variables_url": url,
        "source": source,
        "total_variables": len(rows),
        "match_count": len(filtered),
        "shown": len(shown),
        "variables": shown,
        "hint": (
            "These are candidate codes -- read the labels and choose the one(s) "
            "that match the request; the order is a heuristic, not the answer."
            + (
                f" Nothing matched '{args.search}' among {len(rows)} entries; broaden "
                "the term or omit --search to scan, then decide."
                if args.search and not filtered else ""
            )
        ),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    label = f"{args.module_id}" + (f" / {dataset}" if dataset else "")
    print(f"# {label}: {len(filtered)} of {len(rows)} variables match (source={source})")
    for r in shown:
        concept = f"  [{r['concept']}]" if r["concept"] else ""
        print(f"  {r['code']}\t{r['label']}{concept}")
    if len(filtered) > len(shown):
        print(f"... {len(filtered) - len(shown)} more; narrow with --search or raise --limit.")
    return 0


def _emit_codebook_from_url(
    args: argparse.Namespace, codebook: dict[str, Any], workspace_root: Path, zone: str | None
) -> int:
    """Fetch + cache + search a codebook declared by a module's `codebook.url_template`."""
    template = str(codebook.get("url_template") or "")
    params = dict(codebook.get("params") or {})
    if getattr(args, "year", None):
        params["year"] = args.year
    if args.dataset:
        params["dataset"] = args.dataset
    try:
        url = template.format(**params)
    except KeyError as exc:
        print(
            f"This module's codebook URL needs a {exc} value -- pass it with "
            f"--year/--dataset (known params: {sorted(params)}).",
            file=sys.stderr,
        )
        return 1
    cache_key = _safe_name(url.split("//", 1)[-1])
    cache_path = (
        workspace_root / ".cache" / "variables"
        / _safe_name(args.module_id) / f"{cache_key}.json"
    )
    try:
        data, source = _load_variable_dictionary(url, cache_path, refresh=bool(args.refresh))
    except Exception as exc:
        print(f"Could not fetch codebook from {url}: {exc}", file=sys.stderr)
        return 1
    parser = _CODEBOOK_PARSERS.get(str(codebook.get("format") or "census_variables"), _flatten_variables)
    rows = parser(data)
    return _emit_variable_rows(args, rows, zone=zone, source=source, url=url)


def _code_fields_from_schema(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull documented code fields (variable/indicator/series/...) from input_schema."""
    props = (manifest.get("input_schema") or {}).get("properties") or {}
    fields = []
    for name, spec in props.items():
        spec = spec if isinstance(spec, dict) else {}
        fields.append({
            "field": name,
            "description": (spec.get("description") or "").strip(),
            "examples": spec.get("examples") or ([spec["default"]] if "default" in spec else []),
        })
    return fields


def _emit_schema_fallback(
    args: argparse.Namespace, manifest: dict[str, Any], module_dir: Path, zone: str | None
) -> int:
    """No catalog/codebook: serve the documented codes so the AI still has guidance.

    This keeps the command from dead-ending for providers whose codes live in the
    module manifest + schema.sample (vdem, undp_hdr, naep, atus). The agent reads
    these and decides; for codes not shown here it should consult the source's
    published codebook (link in the description) rather than guess.
    """
    sample = module_dir / "schema.sample.json"
    payload = {
        "module_id": args.module_id,
        "zone": zone,
        "mode": "documented_codes",
        "description": (manifest.get("description") or "").strip(),
        "fields": _code_fields_from_schema(manifest),
        "schema_sample": str(sample) if sample.exists() else None,
        "hint": (
            "This module has no bundled/live codebook. The codes it accepts are "
            "documented above and in the source's own codebook (see description). "
            "Read those and choose; if a code isn't documented, tell the user you "
            "need the provider's codebook rather than guessing."
        ),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"# {args.module_id}: no codebook -- documented codes from the manifest")
    for f in payload["fields"]:
        print(f"  {f['field']}: {f['description'][:80]}  examples={f['examples']}")
    print(payload["hint"])
    return 0


def cmd_module_variables(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    module_dir, zone = _resolve_module_dir(workspace_root, args.module_id)
    if module_dir is None:
        print(f"Module not found: {args.module_id}", file=sys.stderr)
        return 1

    # 1) A module may declare its codebook explicitly (live dictionary URL). This
    #    is how code-based providers without a DCAT catalog (census.decennial,
    #    census.htops, wgi) expose real codes -- fetched once, then cached.
    manifest = _load_manifest(module_dir)
    codebook = manifest.get("codebook")
    if isinstance(codebook, dict) and codebook.get("url_template"):
        return _emit_codebook_from_url(args, codebook, workspace_root, zone)

    catalog = _load_catalog(module_dir)
    if catalog is None:
        # No catalog/codebook -> serve documented codes instead of dead-ending.
        return _emit_schema_fallback(args, manifest, module_dir, zone)

    # Provider catalogs that ship their codebook directly (no DCAT `datasets`
    # list) -> surface those bundled code lists instead of a per-dataset lookup.
    if not catalog.get("datasets"):
        return _emit_bundled_codebook(args, catalog, zone)

    # Without an explicit dataset, behave as dataset discovery: list candidates so
    # the agent can pick the exact id before looking up its variable codes.
    if not args.dataset:
        implicit_search: str | None = None
        if args.search:
            candidates = _match_datasets(catalog, args.search)
        else:
            # A DCAT catalog can list ~1,800 datasets and bury the module's own
            # family under decades of unrelated ones; seed the filter from the
            # module id so the relevant datasets surface first.
            tokens = _module_seed_tokens(args.module_id)
            candidates = _datasets_matching_tokens(catalog.get("datasets") or [], tokens)
            if candidates:
                implicit_search = " ".join(tokens)
            else:
                candidates = list(catalog.get("datasets") or [])
        candidates = sorted(candidates, key=_dataset_recency_key, reverse=True)
        listed = [
            {
                "dataset": _dataset_short_id(d.get("identifier")),
                "identifier": d.get("identifier"),
                "title": d.get("title"),
                "temporal": d.get("temporal"),
            }
            for d in candidates[: args.limit]
        ]
        hint = "Re-run with --dataset <id> --search <concept> to resolve variable codes."
        if implicit_search:
            hint = (
                f"Showing datasets matching '{implicit_search}' (derived from the "
                f"module id), newest first. Pass --search to look elsewhere. " + hint
            )
        payload = {
            "module_id": args.module_id,
            "zone": zone,
            "mode": "datasets",
            "implicit_search": implicit_search,
            "match_count": len(candidates),
            "shown": len(listed),
            "datasets": listed,
            "hint": hint,
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, default=str))
            return 0
        print(f"# {args.module_id}: {len(candidates)} dataset(s) match '{args.search or implicit_search or ''}'")
        for d in listed:
            print(f"  {d['dataset']}\t{d['title']}")
        print(payload["hint"])
        return 0

    matches = _match_datasets(catalog, args.dataset)
    if not matches:
        print(
            f"No dataset matching '{args.dataset}' in {args.module_id}. "
            "Run without --dataset (optionally with --search) to list candidates.",
            file=sys.stderr,
        )
        return 1
    dataset = matches[0]
    url = _variables_url_for(dataset)
    if url is None:
        print(
            f"Dataset '{_dataset_short_id(dataset.get('identifier'))}' has no variable "
            "dictionary link (no describedBy and no API accessURL). Check the source docs.",
            file=sys.stderr,
        )
        return 1

    dataset_id = _dataset_short_id(dataset.get("identifier")) or _safe_name(args.dataset)
    cache_path = (
        workspace_root / ".cache" / "variables"
        / _safe_name(args.module_id) / f"{_safe_name(dataset_id)}.json"
    )
    try:
        data, source = _load_variable_dictionary(url, cache_path, refresh=bool(args.refresh))
    except Exception as exc:
        print(f"Could not fetch variable dictionary from {url}: {exc}", file=sys.stderr)
        return 1

    rows = _flatten_variables(data)
    return _emit_variable_rows(
        args, rows, zone=zone, source=source, url=url,
        dataset=dataset_id, dataset_title=dataset.get("title"),
    )


def add_module_inspect_subcommands(module_sub: argparse._SubParsersAction) -> None:
    show = module_sub.add_parser("show", help="Show a module's manifest, schema, override status, and last run")
    show.add_argument("module_id")
    show.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    show.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    show.set_defaults(func=cmd_module_show)

    files = module_sub.add_parser("files", help="List the files Sancho installed for a module")
    files.add_argument("module_id")
    files.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    files.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    files.set_defaults(func=cmd_module_files)

    status = module_sub.add_parser("status", help="Report install/override status and last successful/failed run")
    status.add_argument("module_id")
    status.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    status.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    status.set_defaults(func=cmd_module_status)

    docs = module_sub.add_parser("docs", help="List doc pointers for a module (markdown, catalog.meta, schema.sample)")
    docs.add_argument("module_id")
    docs.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    docs.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    docs.set_defaults(func=cmd_module_docs)

    variables = module_sub.add_parser(
        "variables",
        help="Resolve real variable/field codes from a dataset's dictionary instead of guessing",
    )
    variables.add_argument("module_id")
    variables.add_argument(
        "--dataset",
        help="Dataset id from the catalog (e.g. ACSDP5Y2023). Omit to list matching datasets.",
    )
    variables.add_argument(
        "--year",
        help="Year for modules whose codebook URL is year-specific (e.g. census.decennial).",
    )
    variables.add_argument(
        "--search",
        help="Filter variables (or datasets) by terms matching code, label, or concept.",
    )
    variables.add_argument("--code", help="Look up an exact code or code prefix (e.g. DP05_0047E).")
    variables.add_argument("--limit", type=int, default=60, help="Max rows to show (default: 60).")
    variables.add_argument(
        "--refresh", action="store_true", help="Re-download the dictionary instead of using cache."
    )
    variables.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    variables.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    variables.set_defaults(func=cmd_module_variables)
