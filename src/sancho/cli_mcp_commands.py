from __future__ import annotations

import argparse
from pathlib import Path

from sancho.mcp.config import claude_desktop_config_path, install_claude_desktop_config, write_client_config
from sancho.mcp.quick import ensure_quick_workspace, resolve_quick_home
from sancho.mcp.server import MCPPolicy, serve_http, serve_stdio
from sancho.workspace import find_workspace_root


def _resolve_workspace_arg(path_arg: str) -> Path:
    return find_workspace_root(Path(path_arg).resolve())


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    if args.quick:
        quick_state = ensure_quick_workspace(
            profile=args.profile,
            modules_csv=args.modules,
            quick_home=args.quick_home,
            sync=args.sync,
            install_targets=True,
        )
        workspace_root = quick_state.workspace_root
        policy = MCPPolicy(
            fetch_only=True,
            allowlisted_module_ids=set(quick_state.allowlisted_fetch_module_ids),
        )
        if quick_state.installed_module_ids:
            print(
                "Quick mode installed/reconciled modules: "
                f"{', '.join(quick_state.installed_module_ids)}"
            )
        print(f"Quick MCP workspace: {workspace_root}")
        if args.transport == "stdio":
            serve_stdio(
                workspace_root,
                policy=policy,
                quick_mode=True,
                quick_profile=quick_state.selection.profile,
                quick_targets=quick_state.selection.resolved_targets,
                quick_modules=quick_state.selection.resolved_modules,
            )
            return 0
        serve_http(
            workspace_root,
            host=args.host,
            port=args.port,
            policy=policy,
            quick_mode=True,
            quick_profile=quick_state.selection.profile,
            quick_targets=quick_state.selection.resolved_targets,
            quick_modules=quick_state.selection.resolved_modules,
        )
        return 0

    workspace_root = _resolve_workspace_arg(args.workspace)
    if args.transport == "stdio":
        serve_stdio(workspace_root)
        return 0
    serve_http(workspace_root, host=args.host, port=args.port)
    return 0


def cmd_mcp_config(args: argparse.Namespace) -> int:
    quick_home = resolve_quick_home(args.quick_home) if args.quick else None
    if args.quick:
        workspace_root = ensure_quick_workspace(
            profile=args.profile,
            modules_csv=args.modules,
            quick_home=quick_home,
            sync=False,
            install_targets=False,
        ).workspace_root
    else:
        workspace_root = _resolve_workspace_arg(args.workspace)

    config_payload = write_client_config(
        client=args.client,
        workspace_root=workspace_root,
        quick=args.quick,
        profile=args.profile,
        modules_csv=args.modules,
        quick_home=quick_home,
        transport=args.transport,
        host=args.host,
        port=args.port,
        sync=args.sync,
    )
    print(f"Wrote MCP client config snippet: {config_payload}")

    if getattr(args, "install", False) and args.client == "claude-desktop":
        import json

        snippet = json.loads(config_payload.read_text(encoding="utf-8"))
        server_def = snippet["mcpServers"]["sancho"]
        installed_path = install_claude_desktop_config(server_def)
        print(f"Installed Sancho Fetch server into Claude Desktop config: {installed_path}")
        print("Restart Claude Desktop to pick up the new MCP server.")
        return 0

    target = claude_desktop_config_path()
    if args.client == "claude-desktop" and target:
        print(f"\nTo activate: copy the mcpServers block into {target}")
        print("Or re-run with --install to do it automatically.")

    return 0
