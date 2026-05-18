"""``sancho setup`` -- one-shot workspace, library, skills, MCP, and sample-module setup."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.constants import WORKSPACE_DIRNAME
from sancho.library import library_config_path, register_library
from sancho.modules import install_target
from sancho.setup_support import SetupReport, SetupStep, install_skills
from sancho.workspace import initialize_workspace

def _check_python() -> SetupStep:
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        return SetupStep("python", "ok", f"{major}.{minor}.{sys.version_info[2]}")
    return SetupStep(
        "python",
        "fail",
        f"Found {major}.{minor}; Sancho needs Python 3.11+.",
        error_code="python_too_old",
        safe_retry="Install Python 3.11+ or rerun the installer so uv can choose a compatible Python.",
        user_action_required=True,
    )


def _check_uv() -> SetupStep:
    uv = shutil.which("uv")
    if not uv:
        return SetupStep("uv", "warn", "Not installed. Install from https://docs.astral.sh/uv/ to manage Sancho easily.")
    try:
        result = subprocess.run([uv, "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return SetupStep("uv", "warn", f"Found at {uv} but couldn't run --version.")
    version = result.stdout.strip() or result.stderr.strip()
    return SetupStep("uv", "ok", version)


def _check_node() -> SetupStep:
    node = shutil.which("node")
    if not node:
        return SetupStep("node", "skip", "Not installed (only needed for the npm wrapper).")
    try:
        result = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return SetupStep("node", "skip", "Found but couldn't run --version.")
    version = result.stdout.strip()
    if version.startswith("v"):
        major = int(version[1:].split(".", 1)[0]) if version[1:].split(".", 1)[0].isdigit() else 0
        if major >= 18:
            return SetupStep("node", "ok", version)
    return SetupStep("node", "warn", f"Found {version}; the npm wrapper expects Node 18+.")


def _ensure_workspace(base_path: Path) -> tuple[SetupStep, Path]:
    workspace = base_path / WORKSPACE_DIRNAME
    if workspace.exists():
        return SetupStep("workspace", "ok", f"already at {workspace}"), workspace
    try:
        ws = initialize_workspace(base_path=base_path, subdir=WORKSPACE_DIRNAME, mode="operator")
    except Exception as exc:
        return SetupStep(
            "workspace",
            "fail",
            f"init failed: {exc}",
            error_code="workspace_init_failed",
            safe_retry=f"sancho setup --path {base_path} --install-claude-desktop",
            user_action_required=False,
        ), workspace
    return SetupStep("workspace", "ok", f"created at {ws}"), ws


def _register_library(repo: Path) -> SetupStep:
    try:
        record = register_library(repo)
    except Exception as exc:
        return SetupStep(
            "library_register",
            "fail",
            f"register failed: {exc}",
            error_code="library_register_failed",
            safe_retry=f"sancho setup --path {repo} --install-claude-desktop",
            user_action_required=False,
        )
    return SetupStep(
        "library_register",
        "ok",
        f"pointer={library_config_path()} -> {record.primary_repo}",
    )


def _smoke_test(workspace_root: Path) -> SetupStep:
    """No-key setup check: add fetch.world_bank without calling the network.

    We deliberately don't call out to the real network in setup; instead
    we verify the install/runtime path is wired up. Real fetch happens in
    the user's first ``sancho fetch sample`` invocation.
    """
    try:
        installed = install_target(workspace_root, target_id="fetch.world_bank", discover=False)
    except Exception as exc:
        return SetupStep("smoke", "warn", f"sample module install failed: {exc}")
    not_ready = [result for result in installed if result.catalog_state == "not_ready_catalog_missing"]
    if not_ready:
        detail = "; ".join(f"{result.module_id}: {result.detail}" for result in not_ready)
        return SetupStep(
            "smoke",
            "fail",
            detail,
            error_code="sample_module_not_ready",
            safe_retry=f"sancho add fetch.world_bank --workspace {workspace_root.parent} --discover",
            user_action_required=False,
        )
    installed_ids = ", ".join(result.module_id for result in installed)
    return SetupStep(
        "smoke",
        "ok",
        f"{installed_ids} installed; run 'sancho fetch sample world_bank' to pull data.",
    )


def _write_mcp_config_snippets(workspace_root: Path) -> tuple[SetupStep, list[Path]]:
    """Write local MCP config snippets for desktop clients.

    We do not blindly edit every app's config file. The snippets live in the
    workspace and can be installed/copied by the AI assistant for the user's
    specific client.
    """
    try:
        from sancho.mcp.config import write_client_config

        written = [
            write_client_config(client=client, workspace_root=workspace_root)
            for client in ("claude-desktop", "cursor", "vscode")
        ]
    except Exception as exc:
        return SetupStep("mcp_config", "warn", f"could not write MCP config snippets: {exc}"), []
    return SetupStep(
        "mcp_config",
        "ok",
        f"wrote {len(written)} desktop MCP config snippet(s) under {workspace_root / 'mcp'}",
    ), written


def _install_claude_desktop_mcp(workspace_root: Path) -> tuple[SetupStep, Path | None]:
    try:
        from sancho.mcp.config import generate_client_config, install_claude_desktop_config

        snippet = generate_client_config("claude-desktop", workspace_root)
        server_def = snippet["mcpServers"]["sancho"]
        installed = install_claude_desktop_config(server_def)
    except Exception as exc:
        return SetupStep(
            "claude_desktop_config",
            "warn",
            f"could not install Claude Desktop MCP config automatically: {exc}",
        ), None
    return SetupStep(
        "claude_desktop_config",
        "ok",
        f"installed Sancho MCP server entry at {installed}; restart Claude Desktop",
    ), installed


def run_setup(
    base_path: Path,
    *,
    skip_smoke_check: bool = False,
    register: bool = True,
    install_claude_desktop: bool = False,
) -> SetupReport:
    report = SetupReport()
    report.add(_check_python())
    report.add(_check_uv())
    report.add(_check_node())

    workspace_step, workspace = _ensure_workspace(base_path.resolve())
    report.workspace_root = workspace
    report.add(workspace_step)

    if register and not report.has_failures:
        report.add(_register_library(base_path.resolve()))
        if not report.has_failures:
            report.library_pointer = library_config_path()
    elif not register:
        report.add(SetupStep("library_register", "skip", "skipped by --no-register"))

    if not report.has_failures:
        skill_step, installed = install_skills()
        report.skills_installed = installed
        report.add(skill_step)

    if not report.has_failures:
        mcp_step, mcp_configs = _write_mcp_config_snippets(workspace)
        report.mcp_configs_written = mcp_configs
        report.add(mcp_step)

    if install_claude_desktop and not report.has_failures:
        claude_step, installed_path = _install_claude_desktop_mcp(workspace)
        report.claude_desktop_config_installed = installed_path
        report.add(claude_step)

    if not skip_smoke_check and not report.has_failures:
        report.add(_smoke_test(workspace))

    if register and not skip_smoke_check and not report.has_failures:
        from sancho.cli_ready import ready_payload

        report.ready_payload = ready_payload(workspace_arg=str(base_path.resolve()))
        if not report.ready_payload.get("ready"):
            report.add(
                SetupStep(
                    "ready",
                    "fail",
                    "post-setup verification failed",
                    error_code="ready_check_failed",
                    safe_retry=f"sancho ready --workspace {base_path.resolve()} --json",
                    user_action_required=False,
                )
            )
        else:
            report.add(SetupStep("ready", "ok", "sancho ready --json passed"))

    return report


def cmd_setup(args: argparse.Namespace) -> int:
    base_path = Path(args.path).resolve()
    report = run_setup(
        base_path,
        skip_smoke_check=bool(args.skip_smoke_check),
        register=not bool(args.no_register),
        install_claude_desktop=bool(args.install_claude_desktop),
    )
    payload: dict[str, Any] = {
        "sancho_version": SANCHO_VERSION,
        "workspace_root": str(report.workspace_root) if report.workspace_root else None,
        "library_pointer": str(report.library_pointer) if report.library_pointer else None,
        "skills_installed_count": len(report.skills_installed),
        "mcp_configs_written": [str(path) for path in report.mcp_configs_written],
        "claude_desktop_config_installed": (
            str(report.claude_desktop_config_installed)
            if report.claude_desktop_config_installed
            else None
        ),
        "steps": [step.to_dict() for step in report.steps],
        "ready": report.ready_payload,
        "has_failures": report.has_failures,
    }
    failed = next((step for step in report.steps if step.status == "fail"), None)
    if failed:
        payload["failed_step"] = failed.name
        payload["error_code"] = failed.error_code or f"{failed.name}_failed"
        payload["safe_retry"] = failed.safe_retry
        payload["user_action_required"] = failed.user_action_required
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 1 if report.has_failures else 0
    print(f"Sancho Fetch setup (sancho {SANCHO_VERSION})")
    print("=" * 38)
    for step in report.steps:
        label = {
            "python": "Python",
            "uv": "Package manager",
            "node": "Node",
            "workspace": "Workspace folder",
            "library_register": "Computer-wide library pointer",
            "skills": "AI assistant skills",
            "mcp_config": "Desktop MCP config snippets",
            "claude_desktop_config": "Claude Desktop MCP config",
            "smoke": "Built-in sample module install check",
            "ready": "Sancho ready verification",
        }.get(step.name, step.name)
        status = {
            "ok": "OK",
            "warn": "Needs attention",
            "skip": "Skipped",
            "fail": "Failed",
        }.get(step.status, step.status)
        print(f"- {status}: {label}" + (f" -- {step.detail}" if step.detail else ""))
    if report.workspace_root:
        print()
        print(f"Workspace: {report.workspace_root}")
    if report.library_pointer:
        print(f"Library pointer: {report.library_pointer}")
    if report.has_failures:
        print()
        print("Setup did not complete cleanly. Ask the AI to run `sancho ready --json` and repair the failed step above.")
        return 1
    print()
    print("You're set up.")
    print("Next: open this folder in Codex, Claude Code, Cursor, or another AI workspace and ask for the data you want.")
    if report.claude_desktop_config_installed:
        print(f"Claude Desktop: Sancho was added to {report.claude_desktop_config_installed}. Fully restart Claude Desktop.")
    elif getattr(args, "install_claude_desktop", False):
        print("Claude Desktop: automatic config install was not available. Use the generated snippet in sancho-workspace/mcp/ if your desktop client supports local MCP.")
    else:
        print("Claude Desktop: run `sancho mcp config --client claude-desktop --workspace . --install`, then fully restart Claude Desktop.")
    print("For API keys, ask the AI to open the private .env file and walk you through the provider signup.")
    return 0


def add_setup_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("setup", help="One-shot setup (workspace + library + skills + MCP + sample module)")
    parser.add_argument("--path", default=".", help="Base directory where sancho-workspace/ will live (default: CWD)")
    parser.add_argument(
        "--skip-smoke-check",
        action="store_true",
        help="Skip the no-network sample module install check",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        dest="skip_smoke_check",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--no-register", action="store_true", help="Skip writing the global library pointer")
    parser.add_argument(
        "--install-claude-desktop",
        action="store_true",
        help="Merge the Sancho MCP server entry into Claude Desktop config (backs up existing config)",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.set_defaults(func=cmd_setup)
