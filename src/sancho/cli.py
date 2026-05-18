from __future__ import annotations

import argparse
import json
import sys

from sancho import __version__
from sancho.cli_export import cmd_export
from sancho.cli_fetch_commands import cmd_fetch_catalog, cmd_fetch_run, cmd_fetch_sample
from sancho.cli_inventory import cmd_inventory
from sancho.cli_cache import add_cache_subcommands
from sancho.cli_custom import add_custom_subcommands, add_module_compare_subcommand
from sancho.cli_env import add_env_subcommands
from sancho.cli_export_project import add_export_subcommand
from sancho.cli_fetched_data import add_fetched_data_subcommands
from sancho.cli_find import add_find_subcommands
from sancho.cli_library import add_library_subcommands
from sancho.cli_log import add_log_subcommands
from sancho.cli_repair import add_repair_subcommands
from sancho.cli_setup import add_setup_subcommand
from sancho.cli_update import add_update_subcommands
from sancho.cli_mcp_commands import cmd_mcp_config, cmd_mcp_serve
from sancho.cli_mode import add_mode_subcommand
from sancho.cli_module_commands import cmd_module_audit, cmd_module_catalog_refresh
from sancho.cli_module_inspect import add_module_inspect_subcommands
from sancho.cli_ready import add_ready_subcommand
from sancho.cli_workspace_commands import cmd_add, cmd_doctor, cmd_init, cmd_run
from sancho.constants import CLIENT_NAMES, WORKSPACE_DIRNAME
from sancho.mcp.quick import DEFAULT_QUICK_PROFILE, QUICK_PROFILE_PACKS
from sancho.runtime.errors import SanchoError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sancho", description="Sancho Fetch CLI")
    parser.add_argument("--version", action="version", version=f"sancho {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser(
        "inventory",
        help="List built-in starter packs and fetch providers",
    )
    inventory_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    inventory_parser.set_defaults(func=cmd_inventory, mode="all")

    packs_parser = subparsers.add_parser("packs", help="List built-in starter packs")
    packs_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    packs_parser.set_defaults(func=cmd_inventory, mode="packs")

    providers_parser = subparsers.add_parser("providers", help="List built-in fetch providers")
    providers_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    providers_parser.set_defaults(func=cmd_inventory, mode="providers")

    init_parser = subparsers.add_parser("init", help="Initialize Sancho Fetch workspace")
    init_parser.add_argument("--path", default=".", help="Base directory where sancho-workspace/ is created")
    init_parser.add_argument("--subdir", default=WORKSPACE_DIRNAME, help="Workspace folder name")
    init_parser.add_argument(
        "--mode",
        choices=["operator", "coder"],
        default=None,
        help="Deprecated and ignored. Pass --yes to skip the confirmation prompt.",
    )
    init_parser.add_argument("--yes", action="store_true", help="Non-interactive confirmation")
    init_parser.set_defaults(func=cmd_init)

    add_parser = subparsers.add_parser("add", help="Install a managed module or pack")
    add_parser.add_argument("module_id")
    add_parser.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    add_parser.add_argument("--channel", default="stable")
    add_parser.add_argument(
        "--discover",
        action="store_true",
        help="Run live provider discovery during install (opt-in). Default fetches prebuilt catalogs.",
    )
    add_parser.set_defaults(func=cmd_add)

    # `sancho update` subcommands (check / preview / apply / rollback)
    add_update_subcommands(subparsers)

    run_parser = subparsers.add_parser("run", help="Run module or playbook")
    run_parser.add_argument("target", help="Module ID or playbook filename")
    run_parser.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    run_parser.add_argument("--input", help="Optional JSON object file for module input")
    run_parser.set_defaults(func=cmd_run)

    fetch_parser = subparsers.add_parser("fetch", help="Provider module catalog and direct execution")
    fetch_sub = fetch_parser.add_subparsers(dest="fetch_command", required=True)

    fetch_catalog = fetch_sub.add_parser("catalog", help="List request families in a migrated provider module")
    fetch_catalog.add_argument("provider", help="Provider ID (e.g. world_bank, nyc_open_data)")
    fetch_catalog.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    fetch_catalog.set_defaults(func=cmd_fetch_catalog)

    fetch_run = fetch_sub.add_parser("run", help="Run a provider API request (direct request contract)")
    fetch_run.add_argument("provider", help="Provider ID (migrated large-tier module)")
    fetch_run.add_argument("--path", required=True, help="Provider API path, e.g. /country/all/indicator/SP.POP.TOTL")
    fetch_run.add_argument("--method", default="GET", help="HTTP method (default: GET)")
    fetch_run.add_argument("--base", help="Base alias from catalog family (defaults to module-specific runtime default)")
    fetch_run.add_argument("--params", help="JSON object of endpoint param overrides")
    fetch_run.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        help="Add a single param as key=value. Repeatable. Merged over --params (wins on conflict).",
    )
    fetch_run.add_argument("--body", help="JSON object request body (used for POST-based families such as SODA v3)")
    fetch_run.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    fetch_run.set_defaults(func=cmd_fetch_run)

    fetch_sample = fetch_sub.add_parser(
        "sample",
        help="Pull one canned zero-key dataset (no API key needed). Great first run.",
    )
    fetch_sample.add_argument(
        "provider",
        help="One of: world_bank, usgs.earthquakes, treasury.fiscal_data, federal_register.documents, fema.openfema",
    )
    fetch_sample.add_argument(
        "--workspace",
        default=".",
        help="Project path containing sancho-workspace/",
    )
    fetch_sample.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    fetch_sample.set_defaults(func=cmd_fetch_sample)

    module_parser = subparsers.add_parser("module", help="Provider-module catalog and standards tooling")
    module_sub = module_parser.add_subparsers(dest="module_command", required=True)

    module_catalog = module_sub.add_parser("catalog", help="Provider-module catalog operations")
    module_catalog_sub = module_catalog.add_subparsers(dest="module_catalog_command", required=True)
    module_refresh = module_catalog_sub.add_parser("refresh", help="Refresh module-local catalog artifacts")
    module_refresh.add_argument("module_id", help="Provider module ID (fetch.<provider>)")
    module_refresh.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    module_refresh.add_argument("--offline", action="store_true", help="Disable network discovery; use seed fallback")
    module_refresh.set_defaults(func=cmd_module_catalog_refresh)

    module_audit = module_sub.add_parser("audit", help="Run datasource implementation standard checks")
    module_audit.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    module_audit.add_argument("--json", action="store_true", help="Output audit report as JSON")
    module_audit.set_defaults(func=cmd_module_audit)

    add_module_inspect_subcommands(module_sub)

    doctor_parser = subparsers.add_parser("doctor", help="Validate workspace health")
    doctor_parser.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    doctor_parser.add_argument("--fix", action="store_true", help="Attempt automatic repairs")
    doctor_parser.add_argument("--json", action="store_true", help="Output machine-readable repair status")
    doctor_parser.set_defaults(func=cmd_doctor)

    export_parser = subparsers.add_parser("export", help="Export workspace as zip")
    export_parser.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    export_parser.add_argument("--output", help="Output zip path")
    export_parser.set_defaults(func=cmd_export)

    mcp_parser = subparsers.add_parser("mcp", help="Optional MCP compatibility mode")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command", required=True)

    mcp_serve = mcp_sub.add_parser("serve", help="Expose local modules over MCP-compatible surface")
    mcp_serve.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    mcp_serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    mcp_serve.add_argument("--host", default="127.0.0.1")
    mcp_serve.add_argument("--port", type=int, default=8765)
    mcp_serve.add_argument("--quick", action="store_true", help="Use quick MCP mode with managed quick workspace")
    mcp_serve.add_argument("--profile", choices=sorted(QUICK_PROFILE_PACKS), default=DEFAULT_QUICK_PROFILE)
    mcp_serve.add_argument(
        "--modules",
        help="Comma-separated module/pack/provider tokens to add to quick profile targets",
    )
    mcp_serve.add_argument("--quick-home", help="Quick mode base directory (default: ~/.sancho/mcp-quick)")
    mcp_serve.add_argument("--sync", action="store_true", help="Re-apply quick profile targets even when already installed")
    mcp_serve.set_defaults(func=cmd_mcp_serve)

    mcp_cfg = mcp_sub.add_parser("config", help="Write MCP client config snippet")
    mcp_cfg.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    mcp_cfg.add_argument("--client", required=True, choices=sorted(CLIENT_NAMES))
    mcp_cfg.add_argument("--quick", action="store_true", help="Generate config for quick MCP mode")
    mcp_cfg.add_argument("--profile", choices=sorted(QUICK_PROFILE_PACKS), default=DEFAULT_QUICK_PROFILE)
    mcp_cfg.add_argument(
        "--modules",
        help="Comma-separated module/pack/provider tokens to add to quick profile targets",
    )
    mcp_cfg.add_argument("--quick-home", help="Quick mode base directory (default: ~/.sancho/mcp-quick)")
    mcp_cfg.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    mcp_cfg.add_argument("--host", default="127.0.0.1")
    mcp_cfg.add_argument("--port", type=int, default=8765)
    mcp_cfg.add_argument("--sync", action="store_true", help="Include --sync in generated quick serve command")
    mcp_cfg.add_argument("--install", action="store_true", help="Install config directly into the client app (claude-desktop only)")
    mcp_cfg.set_defaults(func=cmd_mcp_config)

    add_library_subcommands(subparsers)
    add_cache_subcommands(subparsers)
    add_log_subcommands(subparsers)
    add_export_subcommand(subparsers)
    add_find_subcommands(subparsers)
    add_mode_subcommand(subparsers)
    add_ready_subcommand(subparsers)
    add_repair_subcommands(subparsers)
    add_custom_subcommands(subparsers)
    add_module_compare_subcommand(module_sub)
    add_fetched_data_subcommands(subparsers)
    add_env_subcommands(subparsers)
    add_setup_subcommand(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except FileNotFoundError as exc:
        payload = {
            "error_code": "workspace_not_found",
            "failed_step": getattr(args, "command", "unknown"),
            "error_message": str(exc),
            "safe_retry": "sancho setup --path . --install-claude-desktop --json",
            "user_action_required": False,
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2), file=sys.stderr)
            return 1
        print(f"Error: {exc}", file=sys.stderr)
        print("Run 'sancho setup --path . --json' to create and register a workspace.", file=sys.stderr)
        return 1
    except SanchoError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        payload = {
            "error_code": "unhandled_error",
            "failed_step": getattr(args, "command", "unknown"),
            "error_message": str(exc),
            "safe_retry": "sancho doctor --fix --json",
            "user_action_required": False,
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2), file=sys.stderr)
        else:
            print(f"Sancho command failed during '{payload['failed_step']}': {exc}", file=sys.stderr)
            print("Run 'sancho doctor --fix --json' to check your workspace.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
