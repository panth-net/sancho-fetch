from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.mcp.config import generate_client_config, install_claude_desktop_config

pytestmark = pytest.mark.mcp


def test_generate_client_config_for_stdio_clients() -> None:
    payload = generate_client_config("claude-desktop", Path("C:/tmp/workspace"))
    server = payload["mcpServers"]["sancho"]
    assert Path(server["command"]).name.lower().startswith("sancho")
    assert "--transport" in server["args"]
    assert "stdio" in server["args"]


def test_generate_client_config_for_chatgpt_web_uses_streamable_http() -> None:
    payload = generate_client_config("chatgpt-web", Path("C:/tmp/workspace"))
    server = payload["mcpServers"]["sancho"]
    assert server["transport"] == "streamable-http"
    assert server["url"].endswith("/mcp")
    assert server["sse_url"].endswith("/sse")


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
    assert server["sse_url"] == "http://0.0.0.0:9900/sse"
    assert server["health"] == "http://0.0.0.0:9900/health"


def test_install_claude_desktop_config_timestamp_backup_and_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    config_path = fake_home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"mcpServers": {"old": {"command": "old"}}}), encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr("sancho.mcp.config.sys.platform", "win32")

    installed = install_claude_desktop_config({"command": "sancho", "args": ["mcp", "serve"]})

    assert installed == config_path
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["old"]["command"] == "old"
    assert payload["mcpServers"]["sancho"]["command"] == "sancho"
    backups = list(config_path.parent.glob("claude_desktop_config.*.json.bak"))
    assert len(backups) == 1


def test_install_claude_desktop_config_preserves_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    config_path = fake_home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"mcpServers": ', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr("sancho.mcp.config.sys.platform", "win32")

    with pytest.raises(RuntimeError, match="Claude Desktop config JSON is malformed"):
        install_claude_desktop_config({"command": "sancho", "args": ["mcp", "serve"]})

    assert config_path.read_text(encoding="utf-8") == '{"mcpServers": '
    backups = list(config_path.parent.glob("claude_desktop_config.*.json.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == '{"mcpServers": '
