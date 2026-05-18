"""CLI for ``sancho module show / files / status / docs``."""

from __future__ import annotations

import argparse
import json
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
