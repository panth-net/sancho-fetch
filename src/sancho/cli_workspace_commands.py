from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sancho.cli_hints import format_next_steps_after_doctor, format_next_steps_after_init
from sancho.config import load_workspace_config
from sancho.constants import REQUIRED_DIRECTORIES, REQUIRED_FILES, WORKSPACE_DIRNAME
from sancho.module_ops import validate_all_manifests
from sancho.modules import install_target, regenerate_lock
from sancho.runtime.executor import run_module, run_playbook
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


def _maybe_export_project_bundle(workspace_root: Path, module_id: str) -> None:
    """When run from outside the sancho-fetch repo, drop a bundle in CWD."""
    from sancho.cli_cache import _fetched_data_root
    from sancho.project_export import export_record_to_project
    from sancho.run_log import record_run_event
    from sancho.templates.runtime.cache_index import iter_cache_records

    cwd = Path.cwd().resolve()
    repo_root = workspace_root.parent.resolve()
    try:
        cwd.relative_to(repo_root)
        return
    except ValueError:
        pass

    records = [r for r in iter_cache_records(_fetched_data_root(workspace_root)) if r.get("module_id") == module_id]
    if not records:
        return
    records.sort(key=lambda r: r.get("fetched_at", ""), reverse=True)
    record_dir = Path(records[0]["record_dir"])
    try:
        result = export_record_to_project(
            record_dir=record_dir,
            project_root=cwd,
            workspace_root=workspace_root,
            label=module_id,
        )
        record_run_event(
            workspace_root,
            event_type="project_bundle_exported",
            module_id=module_id,
            detail={"bundle_dir": str(result.bundle_dir), "mode": result.mode},
        )
        print(f"[bundle] {result.bundle_dir} ({result.mode})")
    except Exception as exc:  # pragma: no cover - never block runs on bundle failure
        record_run_event(
            workspace_root,
            event_type="project_bundle_failed",
            module_id=module_id,
            detail={"project_root": str(cwd), "error_message": str(exc)},
        )
        print(f"[bundle] skipped: {exc}", file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    input_payload = _load_input_json(args.input)

    possible_playbook = Path(args.target)
    if not possible_playbook.is_absolute():
        possible_playbook = workspace_root / "playbooks" / args.target

    if possible_playbook.exists():
        results = run_playbook(workspace_root, possible_playbook)
        print(json.dumps([result.__dict__ for result in results], indent=2, default=str))
        return 0

    result = run_module(workspace_root, module_id=args.target, input_payload=input_payload)
    print(json.dumps(result.__dict__, indent=2, default=str))
    _maybe_export_project_bundle(workspace_root, args.target)
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

    if not issues:
        if getattr(args, "json", False):
            print(json.dumps({
                "status": "ok",
                "workspace": str(workspace_root),
                "issues": [],
                "fixed": False,
                "safe_retry": f"sancho doctor --workspace {workspace_root} --fix --json",
                "user_action_required": False,
            }, indent=2))
            return 0
        print("Workspace healthy.")
        print(format_next_steps_after_doctor(workspace_root), end="")
        return 0

    if getattr(args, "json", False) and not args.fix:
        print(json.dumps({
            "status": "needs_repair",
            "workspace": str(workspace_root),
            "issues": issues,
            "fixed": False,
            "safe_retry": f"sancho doctor --workspace {workspace_root} --fix --json",
            "user_action_required": False,
        }, indent=2))
        return 1

    print("Doctor report:")
    for issue in issues:
        print(f"- {issue}")

    if args.fix:
        initialize_workspace(
            base_path=workspace_root.parent,
            subdir=workspace_root.name,
            mode=load_workspace_config(workspace_root).get("mode", "operator"),
        )
        regenerate_lock(workspace_root)
        if getattr(args, "json", False):
            remaining = _check_workspace_integrity(workspace_root)
            print(json.dumps({
                "status": "ok" if not remaining else "needs_repair",
                "workspace": str(workspace_root),
                "issues": remaining,
                "fixed": True,
                "safe_retry": f"sancho doctor --workspace {workspace_root} --fix --json",
                "user_action_required": bool(remaining),
            }, indent=2))
            return 0 if not remaining else 1
        print("Applied automatic fixes where possible.")
        return 0

    print("Run 'sancho doctor --fix --json' to attempt automatic repair.")
    return 1
