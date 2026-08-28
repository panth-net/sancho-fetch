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
from sancho.client_integrations import (
    canonical_launch_definition,
    claude_desktop_platform_supported,
    client_adapters,
    direct_stdio_handshake,
)
from sancho.constants import WORKSPACE_DIRNAME
from sancho.install_state import (
    InstallStateError,
    bind_workspace,
    ensure_workspace_identity,
    load_install_state,
    read_workspace_identity,
    save_install_state,
    state_lock,
    workspace_lifecycle_lock_path,
)
from sancho.library import library_config_path, library_status, read_library_record, register_library
from sancho.modules import install_target, locally_edited_module_files
from sancho.setup_support import SetupReport, SetupStep, install_skills
from sancho.utils import file_sha256
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


def _ensure_workspace(base_path: Path) -> tuple[SetupStep, Path]:
    workspace = base_path / WORKSPACE_DIRNAME
    existed = workspace.exists()
    try:
        ws = initialize_workspace(base_path=base_path, subdir=WORKSPACE_DIRNAME, mode="operator")
    except Exception as exc:
        return SetupStep(
            "workspace",
            "fail",
            f"init failed: {exc}",
            error_code="workspace_init_failed",
            safe_retry=f"sancho setup --path {base_path}",
            user_action_required=False,
        ), workspace
    detail = f"validated existing workspace at {ws}" if existed else f"created at {ws}"
    return SetupStep("workspace", "ok", detail), ws


def _register_library(repo: Path, *, replace_unowned: bool = False) -> SetupStep:
    try:
        pointer = library_config_path()
        with state_lock():
            state = load_install_state()
            ownership = state["owned_files"].get(str(pointer))
            if pointer.exists():
                current_digest = file_sha256(pointer)
                current_record = read_library_record()
                same_target = bool(
                    current_record
                    and current_record.primary_repo.resolve() == repo.resolve()
                    and current_record.primary_workspace.resolve()
                    == (repo / WORKSPACE_DIRNAME).resolve()
                )
                if not isinstance(ownership, dict) and same_target:
                    identity = ensure_workspace_identity(current_record.primary_workspace)
                    bind_workspace(state, current_record.primary_workspace, identity)
                    state["owned_files"][str(pointer)] = {
                        "kind": "library-pointer",
                        "sha256": current_digest,
                        "workspace_id": identity["workspace_id"],
                    }
                    save_install_state(state)
                    return SetupStep(
                        "library_register",
                        "ok",
                        f"adopted existing matching pointer={pointer} -> {current_record.primary_repo}",
                    )
                if not isinstance(ownership, dict) and not replace_unowned:
                    return SetupStep(
                        "library_register",
                        "fail",
                        f"unowned library pointer was preserved: {pointer}",
                        error_code="library_pointer_collision",
                        safe_retry=f"sancho setup --path {repo} --switch-workspace --replace-unowned",
                        user_action_required=True,
                    )
                if (
                    isinstance(ownership, dict)
                    and current_digest != ownership.get("sha256")
                    and not replace_unowned
                ):
                    return SetupStep(
                        "library_register",
                        "fail",
                        f"edited library pointer was preserved: {pointer}",
                        error_code="library_pointer_drift",
                        safe_retry=f"sancho setup --path {repo} --switch-workspace --replace-unowned",
                        user_action_required=True,
                    )
            record = register_library(repo)
            identity = ensure_workspace_identity(record.primary_workspace)
            bind_workspace(state, record.primary_workspace, identity)
            state["owned_files"][str(library_config_path())] = {
                "kind": "library-pointer",
                "sha256": file_sha256(library_config_path()),
                "workspace_id": identity["workspace_id"],
            }
            save_install_state(state)
    except Exception as exc:
        return SetupStep(
            "library_register",
            "fail",
            f"register failed: {exc}",
            error_code="library_register_failed",
            safe_retry=f"sancho setup --path {repo}",
            user_action_required=False,
        )
    return SetupStep(
        "library_register",
        "ok",
        f"Registered sancho-fetch library: pointer={library_config_path()} -> {record.primary_repo}",
    )


def _smoke_test(workspace_root: Path, *, allow_local_edits: bool = False) -> SetupStep:
    """No-key setup check: add fetch.world_bank without calling the network.

    We deliberately don't call out to the real network in setup; instead
    we verify the install/runtime path is wired up. Real fetch happens in
    the user's first ``sancho fetch sample`` invocation.
    """
    edited = locally_edited_module_files(
        workspace_root, "fetch.world_bank", workspace_root / "source" / "fetch" / "fetch_world_bank"
    )
    try:
        installed = install_target(
            workspace_root,
            target_id="fetch.world_bank",
            discover=False,
            allow_local_edits=allow_local_edits,
        )
    except Exception as exc:
        return SetupStep("smoke", "warn", f"sample module install failed: {exc}")
    if edited and not allow_local_edits:
        return SetupStep(
            "smoke",
            "warn",
            f"fetch.world_bank installed, but kept your edits to: {', '.join(sorted(edited))}. "
            "Re-run with --allow-local-edits to overwrite them.",
        )
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
            for client in ("claude-desktop", "chatgpt-desktop", "cursor", "vscode")
        ]
    except Exception as exc:
        return SetupStep("mcp_config", "warn", f"could not write MCP config snippets: {exc}"), []
    return SetupStep(
        "mcp_config",
        "ok",
        f"wrote {len(written)} desktop MCP config snippet(s) under {workspace_root / 'mcp'}",
    ), written


def _prepare_install_state(workspace_root: Path) -> SetupStep:
    try:
        load_install_state()
        identity = ensure_workspace_identity(workspace_root)
    except InstallStateError as exc:
        return SetupStep(
            "ownership",
            "fail",
            str(exc),
            error_code="ownership_state_untrusted",
            safe_retry="Restore or repair the ownership record, then rerun `sancho setup`.",
            user_action_required=True,
        )
    return SetupStep(
        "ownership",
        "ok",
        f"workspace ID {identity['workspace_id']} and ownership state validated",
    )


def _bind_install_state(workspace_root: Path) -> SetupStep:
    try:
        identity = read_workspace_identity(workspace_root)
        with state_lock():
            state = load_install_state()
            bind_workspace(state, workspace_root, identity)
            save_install_state(state)
    except InstallStateError as exc:
        return SetupStep(
            "ownership_bind",
            "fail",
            str(exc),
            error_code="ownership_state_untrusted",
            user_action_required=True,
        )
    return SetupStep("ownership_bind", "ok", "workspace ownership binding recorded atomically")


def _configure_clients(
    workspace_root: Path,
    *,
    only_client: str | None = None,
    replace_unowned: bool = False,
    vscode_config_path: Path | None = None,
) -> tuple[SetupStep, list[dict[str, Any]], dict[str, Any]]:
    try:
        launch = canonical_launch_definition(workspace_root)
        adapters = client_adapters(launch, vscode_config_path=vscode_config_path)
    except Exception as exc:
        return SetupStep("clients", "fail", f"could not build the canonical launch definition: {exc}"), [], {}
    if only_client and only_client not in adapters:
        known = ", ".join(sorted(adapters))
        return SetupStep(
            "clients",
            "fail",
            f"unknown client {only_client!r}; choose one of: {known}",
            error_code="unknown_client",
            user_action_required=True,
        ), [], launch.to_dict()
    # Same platform seam the adapters use, so tests and real runs agree.
    can_force = only_client != "claude-desktop" or claude_desktop_platform_supported()
    if only_client and can_force and hasattr(adapters[only_client], "_detected"):
        # An explicit troubleshooting target is deliberate even when the app
        # cannot be discovered from standard install locations.
        adapters[only_client]._detected = True  # type: ignore[attr-defined]
    selected = {only_client: adapters[only_client]} if only_client else {
        name: adapter for name, adapter in adapters.items() if adapter.detect()
    }
    results = [
        adapter.apply(launch, replace_unowned=replace_unowned).to_dict()
        for adapter in selected.values()
    ]
    failed = [item for item in results if item["state"] == "failed"]
    actions = [
        item
        for item in results
        if item["state"] in {"user_action_required", "preserved_drift", "policy_blocked"}
        or (only_client is not None and item["state"] == "absent")
        or item.get("user_action_required")
    ]
    if failed:
        names = ", ".join(item["client"] for item in failed)
        return SetupStep(
            "clients",
            "fail",
            f"client configuration failed safely for: {names}",
            error_code="client_configuration_failed",
            safe_retry=f"sancho setup --client {failed[0]['client']}",
            user_action_required=any(item.get("user_action_required") for item in failed),
        ), results, launch.to_dict()
    if actions:
        names = ", ".join(item["client"] for item in actions)
        return SetupStep(
            "clients",
            "warn",
            f"configuration preserved existing state or needs a restart/action for: {names}",
            user_action_required=True,
        ), results, launch.to_dict()
    if not results:
        return SetupStep(
            "clients",
            "warn",
            "No supported local client was detected. Snippets and current manual setup instructions were generated.",
            user_action_required=True,
        ), results, launch.to_dict()
    return SetupStep("clients", "ok", f"verified {len(results)} detected client registration(s)"), results, launch.to_dict()


def _run_setup_locked(
    base_path: Path,
    *,
    skip_smoke_check: bool = False,
    register: bool = True,
    configure_clients: bool = True,
    only_client: str | None = None,
    replace_unowned: bool = False,
    vscode_config_path: Path | None = None,
    allow_local_edits: bool = False,
) -> SetupReport:
    report = SetupReport()
    report.add(_check_python())
    report.add(_check_uv())

    workspace_step, workspace = _ensure_workspace(base_path.resolve())
    report.workspace_root = workspace
    report.add(workspace_step)

    if not report.has_failures:
        report.add(_prepare_install_state(workspace))

    if register and not report.has_failures:
        report.add(_register_library(base_path.resolve(), replace_unowned=replace_unowned))
        if not report.has_failures:
            report.library_pointer = library_config_path()
    elif not register:
        report.add(SetupStep("library_register", "skip", "skipped by --no-register"))
        if not report.has_failures:
            report.add(_bind_install_state(workspace))

    if not report.has_failures:
        skill_step, installed = install_skills(allow_local_edits=allow_local_edits)
        report.skills_installed = installed
        report.add(skill_step)

    if not report.has_failures:
        mcp_step, mcp_configs = _write_mcp_config_snippets(workspace)
        report.mcp_configs_written = mcp_configs
        report.add(mcp_step)

    if configure_clients and not report.has_failures:
        client_step, clients, launch = _configure_clients(
            workspace,
            only_client=only_client,
            replace_unowned=replace_unowned,
            vscode_config_path=vscode_config_path,
        )
        report.clients = clients
        report.launch = launch
        report.add(client_step)
    elif not configure_clients:
        report.add(SetupStep("clients", "skip", "skipped by --no-client-config"))

    if not skip_smoke_check and not report.has_failures:
        report.add(_smoke_test(workspace, allow_local_edits=allow_local_edits))

    if not report.has_failures:
        launch = canonical_launch_definition(workspace)
        launch_result = direct_stdio_handshake(launch)
        report.add(
            SetupStep(
                "mcp_launch",
                "ok" if launch_result.ok else "fail",
                launch_result.detail,
                error_code=None if launch_result.ok else "mcp_launch_failed",
                safe_retry=None if launch_result.ok else "sancho doctor --fix --json",
                user_action_required=False,
            )
        )

    if register and not report.has_failures:
        from sancho.cli_ready import ready_payload

        report.ready_payload = ready_payload(
            workspace_arg=str(base_path.resolve()),
            require_sample_module=not skip_smoke_check,
        )
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


def run_setup(
    base_path: Path,
    *,
    skip_smoke_check: bool = False,
    register: bool = True,
    configure_clients: bool = True,
    only_client: str | None = None,
    replace_unowned: bool = False,
    vscode_config_path: Path | None = None,
    allow_local_edits: bool = False,
) -> SetupReport:
    workspace = base_path.resolve() / WORKSPACE_DIRNAME
    with state_lock(workspace_lifecycle_lock_path(workspace)):
        return _run_setup_locked(
            base_path,
            skip_smoke_check=skip_smoke_check,
            register=register,
            configure_clients=configure_clients,
            only_client=only_client,
            replace_unowned=replace_unowned,
            vscode_config_path=vscode_config_path,
            allow_local_edits=allow_local_edits,
        )


def cmd_setup(args: argparse.Namespace) -> int:
    if getattr(args, "vscode_profile_path", None) and getattr(args, "client", None) != "vscode":
        detail = "--vscode-profile-path is profile-specific and must be used with --client vscode."
        payload = {
            "sancho_version": SANCHO_VERSION,
            "has_failures": True,
            "failed_step": "workspace_selection",
            "error_code": "vscode_profile_requires_client",
            "detail": detail,
            "user_action_required": True,
            "safe_retry": "sancho setup --client vscode --vscode-profile-path <profile-folder>",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(detail)
        return 1
    requested = Path(args.path).resolve() if args.path else None
    registered = library_status()
    if registered.healthy and registered.record is not None:
        current = registered.record.primary_repo.resolve()
        identity_mismatch = False
        try:
            state = load_install_state()
            bound = state.get("workspace")
            if isinstance(bound, dict):
                try:
                    identity = read_workspace_identity(registered.record.primary_workspace)
                except InstallStateError:
                    identity_mismatch = True
                else:
                    identity_mismatch = bool(
                        bound.get("workspace_id") != identity.get("workspace_id")
                        or Path(str(bound.get("resolved_path", ""))).resolve()
                        != registered.record.primary_workspace.resolve()
                    )
        except InstallStateError as exc:
            payload = {
                "sancho_version": SANCHO_VERSION,
                "has_failures": True,
                "failed_step": "ownership",
                "error_code": "ownership_state_untrusted",
                "detail": str(exc),
                "user_action_required": True,
                "safe_retry": "Restore the ownership record, then rerun `sancho setup`.",
            }
            if getattr(args, "json", False):
                print(json.dumps(payload, indent=2))
            else:
                print(payload["detail"])
            return 1
        if identity_mismatch and not (
            requested is not None and requested == current and bool(args.switch_workspace)
        ):
            detail = (
                "The registered path now contains a different or unidentifiable workspace. "
                "Sancho preserved the current registration instead of silently adopting it."
            )
            payload = {
                "sancho_version": SANCHO_VERSION,
                "has_failures": True,
                "failed_step": "workspace_selection",
                "error_code": "workspace_identity_mismatch",
                "detail": detail,
                "workspace_root": str(registered.record.primary_workspace.resolve()),
                "user_action_required": True,
                "safe_retry": f"sancho setup --path {current} --switch-workspace",
            }
            if getattr(args, "json", False):
                print(json.dumps(payload, indent=2))
            else:
                print(detail)
            return 1
        if requested is None:
            base_path = current
        elif requested == current:
            base_path = current
        elif not bool(args.switch_workspace):
            # Even --no-register must not bypass this: setup would still
            # rebind install-state and every client registration to the new
            # folder, splitting them from the registered workspace.
            detail = (
                f"A healthy workspace is already registered at {current}. "
                "To switch deliberately, rerun with both --path and --switch-workspace."
            )
            payload = {
                "sancho_version": SANCHO_VERSION,
                "has_failures": True,
                "failed_step": "workspace_selection",
                "error_code": "workspace_switch_requires_intent",
                "detail": detail,
                "workspace_root": str(registered.record.primary_workspace.resolve()),
                "user_action_required": True,
                "safe_retry": f"sancho setup --path {requested} --switch-workspace",
            }
            if getattr(args, "json", False):
                print(json.dumps(payload, indent=2))
            else:
                print(detail)
            return 1
        else:
            base_path = requested
    elif registered.record is not None and not registered.healthy:
        # A stale registration is still a registration: re-pointing it needs
        # the same explicit intent as switching a healthy one.
        if requested is None or not bool(args.switch_workspace):
            detail = (
                "The registered workspace is missing or moved. Provide its current path with "
                "--path and confirm the change with --switch-workspace."
            )
            retry_path = str(requested) if requested is not None else "<current-folder>"
            payload = {
                "sancho_version": SANCHO_VERSION,
                "has_failures": True,
                "failed_step": "workspace_selection",
                "error_code": "stale_workspace_requires_path",
                "detail": detail,
                "user_action_required": True,
                "safe_retry": f"sancho setup --path {retry_path} --switch-workspace",
            }
            if getattr(args, "json", False):
                print(json.dumps(payload, indent=2))
            else:
                print(detail)
            return 1
        base_path = requested
    else:
        base_path = requested or Path.cwd().resolve()
    report = run_setup(
        base_path,
        skip_smoke_check=bool(args.skip_smoke_check),
        register=not bool(args.no_register),
        configure_clients=not bool(args.no_client_config),
        only_client=getattr(args, "client", None),
        replace_unowned=bool(getattr(args, "replace_unowned", False)),
        vscode_config_path=(
            Path(args.vscode_profile_path).resolve()
            if getattr(args, "vscode_profile_path", None)
            else None
        ),
        allow_local_edits=bool(getattr(args, "allow_local_edits", False)),
    )
    payload: dict[str, Any] = {
        "sancho_version": SANCHO_VERSION,
        "workspace_root": str(report.workspace_root) if report.workspace_root else None,
        "library_pointer": str(report.library_pointer) if report.library_pointer else None,
        "skills_installed_count": len(report.skills_installed),
        "mcp_configs_written": [str(path) for path in report.mcp_configs_written],
        "clients": report.clients,
        "launch": report.launch,
        "steps": [step.to_dict() for step in report.steps],
        "ready": report.ready_payload,
        "has_failures": report.has_failures,
        "user_action_required": any(step.user_action_required for step in report.steps)
        or any(bool(client.get("user_action_required")) for client in report.clients)
        or bool(report.ready_payload and report.ready_payload.get("user_action_required")),
    }
    failed = next((step for step in report.steps if step.status == "fail"), None)
    if failed:
        payload["failed_step"] = failed.name
        payload["error_code"] = failed.error_code or f"{failed.name}_failed"
        payload["safe_retry"] = failed.safe_retry
        payload["user_action_required"] = bool(payload["user_action_required"] or failed.user_action_required)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 1 if report.has_failures else 0
    print(f"Sancho Fetch setup (sancho {SANCHO_VERSION})")
    print("=" * 38)
    for step in report.steps:
        label = {
            "python": "Python",
            "uv": "Package manager",
            "workspace": "Workspace folder",
            "ownership": "Installation ownership",
            "ownership_bind": "Workspace ownership binding",
            "library_register": "Computer-wide library pointer",
            "skills": "AI assistant skills",
            "mcp_config": "Desktop MCP config snippets",
            "clients": "Detected client configuration",
            "mcp_launch": "Direct MCP launch",
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
        print("Setup did not complete cleanly. Run `sancho ready --json` to diagnose, then `sancho doctor --fix --json` for safe repair.")
        return 1
    print()
    if any(step.user_action_required for step in report.steps) or bool(
        report.ready_payload and report.ready_payload.get("user_action_required")
    ):
        print("Setup finished; complete the reported client actions below.")
    else:
        print("You're set up.")
    print("Sancho is installed computer-wide. You do not need to open this folder again.")
    print("In Claude Desktop, use the Code tab. In Codex, start a Code chat.")
    print("Regular chats cannot access your local Sancho installation.")
    if report.clients:
        for client in report.clients:
            print(f"{client['client']}: {client['state']} — {client['detail']}")
    else:
        print("No supported client was detected; use the generated MCP instructions when you install one.")
    print("For API keys, ask the AI to open the private .env file and walk you through the provider signup.")
    return 0


def add_setup_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("setup", help="One-shot setup (workspace + library + skills + MCP + sample module)")
    parser.add_argument(
        "--path",
        default=None,
        help="Explicit base directory for sancho-workspace/ (bare setup reuses a healthy registration)",
    )
    parser.add_argument(
        "--switch-workspace",
        action="store_true",
        help="Confirm that --path should replace a different healthy or stale library registration",
    )
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
        "--no-client-config",
        action="store_true",
        help="Generate snippets but do not configure detected supported clients",
    )
    parser.add_argument(
        "--client",
        choices=("claude-desktop", "codex", "cursor", "vscode"),
        help="Configure or troubleshoot only one client, even when it is not auto-detected",
    )
    parser.add_argument(
        "--replace-unowned",
        action="store_true",
        help="Explicitly replace/adopt an unowned same-name MCP entry for the selected client",
    )
    parser.add_argument(
        "--vscode-profile-path",
        help="Exact VS Code profile directory or mcp.json path (use with --client vscode)",
    )
    parser.add_argument(
        "--allow-local-edits",
        action="store_true",
        help="Overwrite managed files and skill files you have edited (default: keep yours and warn)",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.set_defaults(func=cmd_setup)
