"""Stable external-workspace bootstrap for the managed-uv Claude MCPB."""

from __future__ import annotations

import os
from pathlib import Path

from sancho.constants import WORKSPACE_DIRNAME
from sancho.install_state import state_lock, workspace_lifecycle_lock_path
from sancho.mcp.server import serve_stdio
from sancho.modules import install_target
from sancho.workspace import initialize_workspace


def extension_workspace() -> Path:
    configured = os.environ.get("SANCHO_MCPB_WORKSPACE", "").strip()
    base = Path(configured).expanduser() if configured else Path.home() / "Sancho Fetch Extension"
    if base.name == WORKSPACE_DIRNAME:
        return base.resolve()
    return (base / WORKSPACE_DIRNAME).resolve()


def bootstrap_workspace() -> Path:
    workspace = extension_workspace()
    # The lock lives in Sancho's control directory, never inside the
    # replaceable extension bundle. It serializes first launch with upgrades
    # or a concurrent CLI run against the same workspace.
    with state_lock(workspace_lifecycle_lock_path(workspace)):
        initialize_workspace(
            base_path=workspace.parent,
            subdir=workspace.name,
            mode="operator",
            allow_identity_migration=False,
        )
        install_target(
            workspace,
            target_id="fetch.world_bank",
            discover=False,
            allow_local_edits=False,
        )
    return workspace


def main() -> None:
    serve_stdio(bootstrap_workspace())


if __name__ == "__main__":
    main()
