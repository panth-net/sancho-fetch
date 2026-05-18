from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from sancho.constants import CLIENT_NAMES
from sancho.mcp.quick import DEFAULT_QUICK_PROFILE


def _sancho_command() -> str:
    """Return a command Claude Desktop can launch without inheriting shell PATH."""
    resolved = shutil.which("sancho")
    if resolved:
        return str(Path(resolved).resolve())
    return "sancho"


def generate_client_config(
    client: str,
    workspace_root: Path,
    *,
    quick: bool = False,
    profile: str = DEFAULT_QUICK_PROFILE,
    modules_csv: str | None = None,
    quick_home: Path | None = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    sync: bool = False,
) -> dict:
    if client not in CLIENT_NAMES:
        known = ", ".join(sorted(CLIENT_NAMES))
        raise ValueError(f"Unsupported client '{client}'. Supported: {known}")

    if client == "chatgpt-web":
        server_def = {
            "transport": "streamable-http",
            "url": f"http://{host}:{port}/mcp",
            "sse_url": f"http://{host}:{port}/sse",
            "health": f"http://{host}:{port}/health",
        }
    else:
        command_args: list[str] = ["mcp", "serve"]
        if quick:
            command_args.extend(["--quick", "--profile", profile])
            if modules_csv:
                command_args.extend(["--modules", modules_csv])
            if quick_home is not None:
                command_args.extend(["--quick-home", str(quick_home)])
            if sync:
                command_args.append("--sync")
        else:
            command_args.extend(["--workspace", str(workspace_root)])

        command_args.extend(["--transport", transport])
        if transport == "http":
            command_args.extend(["--host", host, "--port", str(port)])

        server_def = {
            "command": _sancho_command(),
            "args": command_args,
        }

    return {
        "client": client,
        "mcpServers": {
            "sancho": server_def,
        },
    }


def write_client_config(
    client: str,
    workspace_root: Path,
    *,
    quick: bool = False,
    profile: str = DEFAULT_QUICK_PROFILE,
    modules_csv: str | None = None,
    quick_home: Path | None = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    sync: bool = False,
) -> Path:
    payload = generate_client_config(
        client,
        workspace_root,
        quick=quick,
        profile=profile,
        modules_csv=modules_csv,
        quick_home=quick_home,
        transport=transport,
        host=host,
        port=port,
        sync=sync,
    )
    output_dir = workspace_root / "mcp"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{client}.mcp.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def claude_desktop_config_path() -> Path | None:
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA")
        appdata = (Path(roaming) if roaming else Path.home() / "AppData" / "Roaming") / "Claude"
    elif sys.platform == "darwin":
        appdata = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        return None
    return appdata / "claude_desktop_config.json"


def install_claude_desktop_config(server_def: dict) -> Path:
    config_path = claude_desktop_config_path()
    if config_path is None:
        raise RuntimeError(
            "Automatic install is only supported on Windows and macOS. "
            "Copy the mcpServers block from the generated snippet manually."
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if config_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = config_path.with_name(f"{config_path.stem}.{stamp}{config_path.suffix}.bak")
        shutil.copy2(config_path, backup)
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Claude Desktop config JSON is malformed. "
                f"A backup was preserved at {backup}. "
                f"Fix or replace {config_path} with valid JSON, then rerun setup."
            ) from exc

    mcp_servers = existing.setdefault("mcpServers", {})
    mcp_servers["sancho"] = server_def
    tmp_path = config_path.with_name(f"{config_path.name}.tmp")
    tmp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp_path.replace(config_path)
    return config_path
