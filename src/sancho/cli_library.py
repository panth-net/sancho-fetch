"""CLI for ``sancho library`` (register/show/open/repair) and ``sancho paths``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sancho.constants import WORKSPACE_DIRNAME
from sancho.env_keys import env_status
from sancho.project_export import PROJECT_FOLDER
from sancho.library import (
    LibraryStatus,
    git_status_summary,
    library_config_path,
    library_status,
    open_in_file_manager,
    register_library,
)


def _print_record_lines(status: LibraryStatus) -> None:
    record = status.record
    if record is None:
        print("Library: not registered.")
        print("Run 'sancho library register <path-to-sancho-fetch>' from your visible folder.")
        return
    print(f"Library config: {library_config_path()}")
    print(f"Primary repo:     {record.primary_repo}")
    print(f"Primary workspace: {record.primary_workspace}")
    print(f"Registered at:    {record.registered_at}")
    if status.issues:
        print("Issues:")
        for issue in status.issues:
            print(f"  - {issue}")
        print("Run 'sancho library repair' for guidance.")
    else:
        print("Status: healthy.")


def cmd_library_register(args: argparse.Namespace) -> int:
    record = register_library(Path(args.path))
    print(f"Registered sancho-fetch library at {record.primary_repo}")
    print(f"Workspace: {record.primary_workspace}")
    print(f"Pointer:   {library_config_path()}")
    return 0


def cmd_library_show(args: argparse.Namespace) -> int:
    status = library_status()
    if getattr(args, "json", False):
        record = status.record.to_dict() if status.record else None
        print(json.dumps({"record": record, "issues": status.issues}, indent=2))
        return 0
    _print_record_lines(status)
    return 0 if status.healthy or status.record is None else 1


def cmd_library_open(args: argparse.Namespace) -> int:
    status = library_status()
    if status.record is None:
        print("No library registered. Run 'sancho library register <path>' first.", file=sys.stderr)
        return 1
    if not status.record.primary_repo.exists():
        print(f"Registered repo no longer exists: {status.record.primary_repo}", file=sys.stderr)
        print("Run 'sancho library repair' or re-register the moved folder.", file=sys.stderr)
        return 1
    open_in_file_manager(status.record.primary_repo)
    print(f"Opened {status.record.primary_repo}")
    return 0


def cmd_library_repair(args: argparse.Namespace) -> int:
    status = library_status()
    if status.record is None:
        print("No library registered.")
        print("Recommend: 'sancho library register <path-to-sancho-fetch>'.")
        return 1
    if not status.issues:
        print(f"Library healthy at {status.record.primary_repo}")
        return 0
    print("Library has issues:")
    for issue in status.issues:
        print(f"  - {issue}")
    print()
    print("Recommended fixes:")
    if not status.record.primary_repo.exists():
        print(f"  - The sancho-fetch folder moved or was deleted. If you moved it,")
        print(f"    run: sancho library register <new-path-to-sancho-fetch>")
    elif not status.record.primary_workspace.exists():
        print(f"  - The workspace inside the repo is missing.")
        print(f"    Run: sancho setup --path {status.record.primary_repo} --install-claude-desktop")
    return 1


def _resolve_active_workspace(cwd: Path) -> tuple[Path | None, str]:
    """Pick the workspace Sancho would operate against.

    Order of precedence:
    1. CWD is the workspace folder.
    2. CWD contains a sancho-workspace/.
    3. Registered library pointer.
    """
    if cwd.name == WORKSPACE_DIRNAME and cwd.exists():
        return cwd, "cwd"
    candidate = cwd / WORKSPACE_DIRNAME
    if candidate.exists():
        return candidate, "cwd"
    status = library_status()
    if status.record and status.record.primary_workspace.exists():
        return status.record.primary_workspace, "library"
    return None, "none"


def _paths_payload() -> dict[str, Any]:
    cwd = Path.cwd().resolve()
    workspace, workspace_source = _resolve_active_workspace(cwd)
    lib_status = library_status()
    payload: dict[str, Any] = {
        "current_project": str(cwd),
        "workspace_source": workspace_source,
        "library": {
            "registered": lib_status.record is not None,
            "config_path": str(library_config_path()),
            "record": lib_status.record.to_dict() if lib_status.record else None,
            "issues": lib_status.issues,
        },
        "workspace": None,
    }
    if workspace is not None:
        repo_root = workspace.parent
        env = env_status(workspace)
        payload["workspace"] = {
            "root": str(repo_root),
            "workspace": str(workspace),
            "source": str(workspace / "source"),
            "custom": str(workspace / "custom"),
            "fetched_data": str(workspace / "fetched-data"),
            "analysis_data": str(workspace / "analysis-data"),
            "outputs": str(workspace / "outputs"),
            "logs": str(workspace / "logs"),
            "update_backups": str(workspace / "update-backups"),
            "env_file": str(workspace / ".env"),
            "active_env_file": env["env_path"],
            "project_env_file": env["project_env_path"],
            "env_files_checked": env["env_paths"],
        }
        payload["project_copy_target"] = str(cwd / PROJECT_FOLDER)
        git = git_status_summary(repo_root)
        if git is not None:
            payload["git"] = git
    return payload


def cmd_paths(args: argparse.Namespace) -> int:
    payload = _paths_payload()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0

    if payload["workspace"] is None:
        print("Sancho Fetch: no workspace found.")
        if not payload["library"]["registered"]:
            print("Tip: open your sancho-fetch folder and run 'sancho setup --install-claude-desktop'.")
        else:
            print("Tip: the registered library workspace is missing -- 'sancho library repair'.")
        return 1

    ws = payload["workspace"]
    print("Sancho Fetch paths:")
    print(f"  Root:           {ws['root']}")
    print(f"  Workspace:      {ws['workspace']}")
    print(f"  Source modules: {ws['source']}")
    print(f"  Custom modules: {ws['custom']}")
    print(f"  Fetched data:   {ws['fetched_data']}")
    print(f"  Analysis data:  {ws['analysis_data']}")
    print(f"  Outputs:        {ws['outputs']}")
    print(f"  Logs:           {ws['logs']}")
    print(f"  Update backups: {ws['update_backups']}")
    print(f"  Env file:       {ws['active_env_file']}")
    print()
    print(f"  Current project:      {payload['current_project']}")
    print(f"  Project copy target:  {payload['project_copy_target']}")
    print(f"  Workspace source:     {payload['workspace_source']}")
    print()
    lib = payload["library"]
    if lib["registered"]:
        record = lib["record"]
        print(f"  Library: registered at {record['primary_repo']}")
        if lib["issues"]:
            for issue in lib["issues"]:
                print(f"    issue: {issue}")
    else:
        print("  Library: not registered (using CWD workspace)")
    if "git" in payload:
        git = payload["git"]
        state = "clean" if git["clean"] else f"{git['changed_files']} changed file(s)"
        print(f"  Git status: {state}")
    return 0


def add_library_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Wire ``library`` and ``paths`` subcommands into the root CLI."""
    library = subparsers.add_parser("library", help="Manage the registered sancho-fetch folder")
    library_sub = library.add_subparsers(dest="library_command", required=True)

    register = library_sub.add_parser(
        "register",
        help="Save a pointer to your visible sancho-fetch folder",
    )
    register.add_argument("path", help="Path to your sancho-fetch folder (or its sancho-workspace/)")
    register.set_defaults(func=cmd_library_register)

    show = library_sub.add_parser("show", help="Show the registered library pointer")
    show.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    show.set_defaults(func=cmd_library_show)

    open_cmd = library_sub.add_parser("open", help="Open the registered sancho-fetch folder in your file manager")
    open_cmd.set_defaults(func=cmd_library_open)

    repair = library_sub.add_parser("repair", help="Diagnose a missing or moved library pointer")
    repair.set_defaults(func=cmd_library_repair)

    paths = subparsers.add_parser(
        "paths",
        help="Show every relevant Sancho Fetch path (workspace, source, fetched-data, logs, env)",
    )
    paths.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    paths.set_defaults(func=cmd_paths)
