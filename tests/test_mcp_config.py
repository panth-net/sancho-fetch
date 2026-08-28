from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from sancho.mcp.config import generate_client_config

pytestmark = pytest.mark.mcp


def test_generate_client_config_for_stdio_clients() -> None:
    payload = generate_client_config("claude-desktop", Path("C:/tmp/workspace"))
    server = payload["mcpServers"]["sancho"]
    assert Path(server["command"]).name.lower().startswith("sancho")
    assert "--transport" in server["args"]
    assert "stdio" in server["args"]


def test_generate_client_config_prefers_current_sancho_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = tmp_path / "sancho.exe"
    current.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(current)])

    payload = generate_client_config("claude-desktop", Path("C:/tmp/workspace"))

    server = payload["mcpServers"]["sancho"]
    assert Path(server["command"]) == current.resolve()


def test_generate_client_config_for_chatgpt_web_uses_streamable_http() -> None:
    payload = generate_client_config("chatgpt-web", Path("C:/tmp/workspace"))
    server = payload["mcpServers"]["sancho"]
    assert server["transport"] == "streamable-http"
    assert server["url"].endswith("/mcp")
    # The HTTP+SSE transport is deprecated (2026-07-28 spec); no SSE endpoint
    # may be advertised.
    assert "sse_url" not in server


def test_generate_client_config_for_vscode_uses_servers_key() -> None:
    """VS Code's .vscode/mcp.json uses "servers" + a "type" field, not the
    "mcpServers" shape the other clients use."""
    payload = generate_client_config("vscode", Path("C:/tmp/workspace"))
    assert "mcpServers" not in payload
    server = payload["servers"]["sancho"]
    assert server["type"] == "stdio"
    assert Path(server["command"]).name.lower().startswith("sancho")
    assert "--transport" in server["args"]


def test_generate_client_config_for_quick_mode_stdio() -> None:
    payload = generate_client_config(
        "claude-desktop",
        Path("C:/tmp/workspace"),
        quick=True,
        profile="balanced",
        modules_csv="world_bank,pack.us_housing",
        quick_home=Path("C:/tmp/quick-home"),
    )
    server = payload["mcpServers"]["sancho"]
    args = server["args"]
    assert "--quick" in args
    assert "--profile" in args
    assert "balanced" in args
    assert "--modules" in args
    assert "world_bank,pack.us_housing" in args
    assert "--quick-home" in args
    assert str(Path("C:/tmp/quick-home")) in args
    assert "--workspace" not in args


def test_generate_client_config_for_http_url_override() -> None:
    payload = generate_client_config("chatgpt-web", Path("C:/tmp/workspace"), host="0.0.0.0", port=9900)
    server = payload["mcpServers"]["sancho"]
    assert server["url"] == "http://0.0.0.0:9900/mcp"
    assert server["health"] == "http://0.0.0.0:9900/health"
