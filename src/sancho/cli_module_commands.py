from __future__ import annotations

import argparse
import json
from pathlib import Path

from sancho.module_ops import audit_provider_modules, refresh_module_catalog
from sancho.workspace import find_workspace_root


def _resolve_workspace_arg(path_arg: str) -> Path:
    return find_workspace_root(Path(path_arg).resolve())


def cmd_module_catalog_refresh(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    result = refresh_module_catalog(workspace_root, args.module_id, offline=args.offline)
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_module_audit(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    reports = audit_provider_modules(workspace_root)
    overall_ok = all(bool(report.get("ok")) for report in reports)

    if args.json:
        print(json.dumps(reports, indent=2, default=str))
    else:
        for report in reports:
            status = "PASS" if report["ok"] else "FAIL"
            print(
                f"{status} {report['module_id']} ({report['passed']}/{report['total']}) "
                f"[{report['module_dir']}]"
            )
            for check in report["checks"]:
                check_status = "OK" if check["passed"] else "MISSING"
                print(f"  - {check_status} {check['id']}: {check['detail']}")

    if not reports:
        print("No provider modules installed in source/fetch.")
        return 0
    return 0 if overall_ok else 1
