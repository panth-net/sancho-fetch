from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sancho.cli_hints import format_next_steps_after_doctor, format_next_steps_after_init
from sancho.config import load_workspace_config
from sancho.constants import REQUIRED_DIRECTORIES, REQUIRED_FILES, WORKSPACE_DIRNAME
from sancho.module_ops import validate_all_manifests
from sancho.modules import install_target, regenerate_lock
from sancho.utils import file_sha256
from sancho.workspace import find_workspace_root, initialize_workspace


def _resolve_workspace_arg(path_arg: str) -> Path:
    return find_workspace_root(Path(path_arg).resolve())


def cmd_init(args: argparse.Namespace) -> int:
    base_path = Path(args.path).resolve()
    if getattr(args, "mode", None) is not None:
        print(
            "Note: --mode is deprecated and ignored. Pass --yes to skip the confirmation prompt.",
            file=sys.stderr,
        )

    target = base_path / args.subdir if base_path.name != WORKSPACE_DIRNAME else base_path
    if not args.yes:
        answer = input(f"Create Sancho Fetch workspace at '{target}'? [Y/n]: ").strip().lower()
        if answer.startswith("n"):
            print("Init canceled.")
            return 0

    workspace_root = initialize_workspace(base_path=base_path, subdir=args.subdir, mode="operator")
    print(f"Initialized workspace: {workspace_root}")
    print(format_next_steps_after_init(workspace_root), end="")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    installed = install_target(
        workspace_root,
        target_id=args.module_id,
        channel=args.channel,
        discover=bool(getattr(args, "discover", False)),
    )
    not_ready = []
    for result in installed:
        if result.catalog_state == "not_ready_catalog_missing":
            not_ready.append(result)
            print(
                f"Module '{result.module_id}' installed but is not ready: {result.detail}",
                file=sys.stderr,
            )
            continue
        print(
            f"Installed module '{result.module_id}' -> {result.install_path} "
            f"({result.catalog_state})"
        )
    return 1 if not_ready else 0


def _load_input_json(path: str | None) -> dict:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")
    return payload


def _run_result_payload(result: Any, full_output: bool) -> dict[str, Any]:
    """Default output is a summary: the full payload can be tens of KB of JSON,
    and the primary working file already holds the data."""
    payload = dict(result.__dict__)
    if not full_output:
        from sancho.cli_public_export import row_count

        payload["row_count"] = row_count(payload.pop("output", None))
    return payload


def cmd_run(args: argparse.Namespace) -> int:
    from sancho.runtime.executor import run_module, run_playbook

    workspace_root = _resolve_workspace_arg(args.workspace)
    input_payload = _load_input_json(args.input)

    possible_playbook = Path(args.target)
    if not possible_playbook.is_absolute():
        possible_playbook = workspace_root / "playbooks" / args.target

    full_output = bool(getattr(args, "full_output", False))

    from sancho.cli_fetch_commands import _auto_public_export
    from sancho.cli_public_export import print_primary

    if possible_playbook.exists():
        results = run_playbook(workspace_root, possible_playbook)
        record_dirs = [d for r in results for d in r.record_dirs]
        unit_sources = [
            r.cache_status or ("fetched_api" if r.status == "ok" else "failed")
            for r in results
            for _ in r.record_dirs
        ]
        public = _auto_public_export(
            workspace_root,
            record_dirs,
            module_id=possible_playbook.stem,
            unit_sources=unit_sources or None,
            quiet=True,
        )
        print(json.dumps([_run_result_payload(r, full_output) for r in results], indent=2, default=str))
        print_primary(public, stream=sys.stderr)
        return 0

    result = run_module(workspace_root, module_id=args.target, input_payload=input_payload)
    cache_status = result.cache_status or ("fetched_api" if result.status == "ok" else "failed")
    public = _auto_public_export(
        workspace_root,
        list(result.record_dirs),
        module_id=args.target,
        unit_sources=[cache_status] if result.record_dirs else None,
        quiet=True,
    )
    payload = _run_result_payload(result, full_output)
    payload["primary_output_path"] = str(public.primary_path) if public else None
    payload["output_paths"] = [str(p) for p in public.output_paths] if public else []
    payload["export_mode"] = public.mode if public else None
    print(json.dumps(payload, indent=2, default=str))
    print_primary(public, stream=sys.stderr)
    return 0


def _check_workspace_integrity(workspace_root: Path) -> list[str]:
    issues: list[str] = []
    for directory in REQUIRED_DIRECTORIES:
        if not (workspace_root / directory).exists():
            issues.append(f"Missing directory: {directory}")

    for file_name in REQUIRED_FILES:
        if not (workspace_root / file_name).exists():
            issues.append(f"Missing file: {file_name}")

    lock_path = workspace_root / "modules.lock.yaml"
    if lock_path.exists():
        import yaml

        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
        for module_id, entry in (lock.get("modules") or {}).items():
            for rel_path, expected in (entry.get("checksums") or {}).items():
                file_path = workspace_root / rel_path
                if not file_path.exists():
                    issues.append(f"Lock mismatch ({module_id}): missing {rel_path}")
                    continue
                actual = file_sha256(file_path)
                if actual != expected:
                    issues.append(f"Lock mismatch ({module_id}): {rel_path}")

    issues.extend(validate_all_manifests(workspace_root))
    return issues


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    issues = _check_workspace_integrity(workspace_root)
    from sancho.cli_ready import ready_payload

    readiness = ready_payload(str(workspace_root))
    install_issues = [
        f"Installation check {name}: {check.get('detail') or check.get('issues') or 'not ready'}"
        for name, check in readiness["checks"].items()
        if not check.get("ok")
    ]
    all_issues = [*issues, *install_issues]

    if not args.fix:
        payload = {
            "status": "ok" if not all_issues else "needs_repair",
            "workspace": str(workspace_root),
            "issues": all_issues,
            "fixed": False,
            "installation": readiness,
            "safe_retry": f"sancho doctor --workspace {workspace_root} --fix --json",
            "user_action_required": bool(readiness.get("user_action_required")),
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        elif not all_issues:
            print("Workspace and installation healthy.")
            print(format_next_steps_after_doctor(workspace_root), end="")
        else:
            print("Doctor report:")
            for issue in all_issues:
                print(f"- {issue}")
            print("Run 'sancho doctor --fix --json' to attempt safe automatic repair.")
        return 0 if not all_issues else 1

    # Doctor may repair the active installation, but changing which workspace
    # the computer uses requires the explicit setup switch contract. This also
    # keeps a stale or moved pointer from being silently adopted during repair.
    from sancho.library import library_status

    registered = library_status()
    if registered.record is not None and (
        not registered.healthy
        or registered.record.primary_workspace.resolve() != workspace_root.resolve()
    ):
        retry = f"sancho setup --path {workspace_root.parent} --switch-workspace"
        payload = {
            "status": "needs_user_action",
            "workspace": str(workspace_root),
            "issues": all_issues,
            "fixed": False,
            "units": [],
            "clients": [],
            "installation": readiness,
            "safe_retry": retry,
            "user_action_required": True,
            "detail": "Doctor will not change a different or stale global workspace pointer without explicit switch intent.",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(payload["detail"])
            print(f"Safe next step: {retry}")
        return 1

    if issues:
        from sancho.install_state import state_lock, workspace_lifecycle_lock_path

        with state_lock(workspace_lifecycle_lock_path(workspace_root)):
            initialize_workspace(
                base_path=workspace_root.parent,
                subdir=workspace_root.name,
                mode=load_workspace_config(workspace_root).get("mode", "operator"),
            )
            regenerate_lock(workspace_root)

    from sancho.cli_setup import run_setup

    setup_report = run_setup(
        workspace_root.parent,
        skip_smoke_check=False,
        register=True,
        configure_clients=True,
    )
    remaining = _check_workspace_integrity(workspace_root)
    readiness = ready_payload(str(workspace_root))
    success = not remaining and readiness["ready"] and not setup_report.has_failures
    payload = {
        "status": "ok" if success else "needs_repair",
        "workspace": str(workspace_root),
        "issues": remaining,
        "fixed": True,
        "units": [step.to_dict() for step in setup_report.steps],
        "clients": setup_report.clients,
        "installation": readiness,
        "safe_retry": f"sancho doctor --workspace {workspace_root} --fix --json",
        "user_action_required": bool(readiness.get("user_action_required")) or any(
            step.user_action_required for step in setup_report.steps
        ),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print("Applied safe automatic fixes." if success else "Some items still need attention.")
    return 0 if success else 1
