"""CLI for ``sancho env open / check / recommend``.

Never reads or prints secret values. ``open`` reveals the .env path in
the user's editor; ``check`` reports which env-var names are populated
(only names, never values); ``recommend`` takes a natural-language data
request and tells the user which providers + keys they need without ever
touching the values themselves.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from sancho.env_keys import (
    HIDDEN_FILE_HINTS,
    HIDDEN_FILE_HINTS_WINDOWS,
    MODULE_KEYS,
    OPTIONAL_KEY_MODULES,
    env_recommend,
    env_status,
    provider_key_hints,
    read_populated_env_keys,
    resolve_env_edit_path,
)
from sancho.workspace import find_workspace_root


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


_read_env_keys = read_populated_env_keys  # back-compat for any caller of the old name


def _open_in_editor(path: Path) -> None:
    target = str(path)
    system = platform.system()
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        try:
            subprocess.run([editor, target], check=False)
            return
        except (OSError, subprocess.SubprocessError):
            pass
    if system == "Windows" and hasattr(os, "startfile"):
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if system == "Darwin":
        subprocess.run(["open", target], check=False)
        return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.run([opener, target], check=False)
        return
    raise RuntimeError(f"No editor available to open {target}. Set $EDITOR.")


def cmd_env_open(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    env_path = resolve_env_edit_path(workspace_root)
    if not env_path.exists():
        env_example = workspace_root / ".env.example"
        if env_example.exists():
            env_path.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Created {env_path} from .env.example")
        else:
            env_path.write_text("# Sancho Fetch workspace env file\n", encoding="utf-8")
            print(f"Created blank {env_path}")
    if args.provider:
        hints = provider_key_hints(args.provider)
        print(f"# Env keys needed for {args.provider!r}:")
        if not hints:
            print(f"  (no public keys recorded for '{args.provider}'; module may not need one)")
        else:
            for hint in hints:
                print(f"  - {hint['module_id']}: {', '.join(hint['env_keys'])}")
        print()
    print(f"Opening {env_path}")
    print()
    print("Reminders:")
    print("  - Paste your own keys directly into this file. Do not share them with the AI assistant.")
    print("  - Sancho never reads or prints values -- only env-var names.")
    print(f"  - {HIDDEN_FILE_HINTS}")
    print(f"  - {HIDDEN_FILE_HINTS_WINDOWS}")
    print("  - Sign-up URLs and per-key instructions are inside .env.example next to each KEY= line.")
    _open_in_editor(env_path)
    return 0


def cmd_env_check(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    status_payload = env_status(workspace_root)
    env_path = Path(str(status_payload["env_path"]))
    keys_present = set(status_payload["keys_present"])
    providers: list[dict[str, object]] = []
    for module_id, env_keys in sorted(MODULE_KEYS.items()):
        missing = [name for name in env_keys if name not in keys_present]
        providers.append({
            "module_id": module_id,
            "env_keys": env_keys,
            "missing": missing,
            "ready": not missing,
            "keys_optional": module_id in OPTIONAL_KEY_MODULES,
        })
    payload = {
        **status_payload,
        "env_path": str(env_path),
        "env_exists": env_path.exists(),
        "keys_present": sorted(keys_present),
        "providers": providers,
        "ready_count": sum(1 for p in providers if p["ready"]),
        "total_count": len(providers),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(f"env path: {env_path}  exists={env_path.exists()}")
    if payload.get("env_paths"):
        print("env files checked:")
        for row in payload["env_paths"]:
            print(
                f"  - {row['path']}  exists={row['exists']}  "
                f"keys={len(row['keys_present'])}"
            )
        if payload.get("shadowed_keys"):
            print(
                "workspace .env overrides project .env for: "
                + ", ".join(payload["shadowed_keys"])
            )
    print(f"keys present: {len(keys_present)}  ({', '.join(sorted(keys_present)) or '(none)'})")
    print()
    print(f"Providers ready: {payload['ready_count']}/{payload['total_count']}")
    for p in providers:
        status = "OK " if p["ready"] else "NEED"
        opt = " (optional)" if p["keys_optional"] else ""
        print(
            f"  {status}  {p['module_id']}  needs: {', '.join(p['env_keys'])}{opt}"
            + (f"  (missing: {', '.join(p['missing'])})" if p["missing"] else "")
        )
    print()
    print(payload["note"])
    return 0


def cmd_env_recommend(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    query = " ".join(args.query).strip()
    if not query:
        print("Usage: sancho env recommend \"<natural-language description of the data you want>\"")
        return 1
    payload = env_recommend(workspace_root, query, limit=int(args.limit))
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"# Recommendations for: {query!r}")
    print()
    summary = payload["summary"]
    print(
        f"Candidates: {summary['total']}  "
        f"ready={summary['ready']}  "
        f"blocked-on-keys={summary['blocked_on_required_keys']}  "
        f"no-keys-needed={summary['no_keys_needed']}"
    )
    print()
    for row in payload["candidates"]:
        marker = "OK " if row["ready"] else "NEED"
        kind = " (optional)" if row.get("keys_optional") else ""
        keys = row["declared_env_keys"]
        keys_str = ", ".join(keys) if keys else "no keys needed"
        label = f"[pack, {row.get('member_count', 0)} modules]" if row.get("kind") == "pack" else "[module]"
        print(f"  {marker} {row.get('id', row.get('module_id')):<40} {label}  keys: {keys_str}{kind}")
        if row.get("description"):
            print(f"        {row['description'][:140]}")
        if row["missing_keys"]:
            print(f"        missing: {', '.join(row['missing_keys'])}")
    print()
    if payload.get("env_example_path"):
        print(f"Sign-up URLs and step-by-step instructions for every key live in:")
        print(f"  {payload['env_example_path']}")
        print(f"Open that file and search for the KEY= line you need.")
        print()
    for step in payload["next_steps"]:
        print(f"- {step}")
    return 0


def add_env_subcommands(subparsers: argparse._SubParsersAction) -> None:
    env = subparsers.add_parser(
        "env", help="Open or check Sancho .env files (never prints values)"
    )
    env_sub = env.add_subparsers(dest="env_command", required=True)

    open_p = env_sub.add_parser("open", help="Open the most helpful Sancho .env in your default editor")
    open_p.add_argument("provider", nargs="?", help="Show which env vars a provider needs (e.g. 'zillow', 'census')")
    open_p.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    open_p.set_defaults(func=cmd_env_open)

    check = env_sub.add_parser("check", help="Report which env-var names are populated (never reads values)")
    check.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    check.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    check.set_defaults(func=cmd_env_check)

    recommend = env_sub.add_parser(
        "recommend",
        help="Given a natural-language description, name the providers and env vars you'll need (values never read).",
    )
    recommend.add_argument("query", nargs="+", help="Free text, e.g. 'housing affordability across US cities'")
    recommend.add_argument("--limit", default="8", help="Max candidate providers to consider (default 8)")
    recommend.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    recommend.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    recommend.set_defaults(func=cmd_env_recommend)


# Back-compat re-exports for any module that imported these from cli_env.
__all__ = [
    "MODULE_KEYS",
    "OPTIONAL_KEY_MODULES",
    "add_env_subcommands",
    "cmd_env_check",
    "cmd_env_open",
    "cmd_env_recommend",
    "provider_key_hints",
    "read_populated_env_keys",
]
