"""Ownership-aware MCP client adapters used by setup, ready, repair, and uninstall."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sancho import __version__ as SANCHO_VERSION
from sancho.install_state import (
    WORKSPACE_SCHEMA_MAX_READER,
    WORKSPACE_SCHEMA_MIN_READER,
    InstallStateError,
    atomic_write_json,
    bind_workspace,
    load_install_state,
    read_workspace_identity,
    save_install_state,
    state_lock,
)
from sancho.mcp.config import _sancho_command


@dataclass(frozen=True)
class LaunchDefinition:
    server_name: str
    executable: str
    arguments: tuple[str, ...]
    transport: str
    environment: dict[str, str]
    workspace_id: str
    workspace_path: str
    workspace_selection: str
    package_version: str
    workspace_schema_min: int
    workspace_schema_max: int

    def stdio_server(self, *, include_type: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "command": self.executable,
            "args": list(self.arguments),
        }
        if self.environment:
            payload["env"] = dict(self.environment)
        if include_type:
            payload = {"type": "stdio", **payload}
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "executable": self.executable,
            "arguments": list(self.arguments),
            "transport": self.transport,
            "environment": dict(self.environment),
            "workspace_id": self.workspace_id,
            "workspace_path": self.workspace_path,
            "workspace_selection": self.workspace_selection,
            "package_version": self.package_version,
            "workspace_schema_range": [self.workspace_schema_min, self.workspace_schema_max],
        }


@dataclass
class ClientResult:
    client: str
    state: str
    detail: str
    detected: bool = True
    changed: bool = False
    user_action_required: bool = False
    safe_retry: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.state in {
            "absent",
            "configured",
            "launch_verified",
            "restart_required",
            "removed",
            "unchanged",
        }

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "client": self.client,
            "state": self.state,
            "detail": self.detail,
            "detected": self.detected,
            "changed": self.changed,
            "user_action_required": self.user_action_required,
        }
        if self.safe_retry:
            payload["safe_retry"] = self.safe_retry
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def canonical_launch_definition(workspace_root: Path) -> LaunchDefinition:
    identity = read_workspace_identity(workspace_root)
    return LaunchDefinition(
        server_name="sancho",
        executable=_sancho_command(),
        arguments=(
            "mcp",
            "serve",
            "--workspace",
            str(workspace_root.resolve()),
            "--transport",
            "stdio",
        ),
        transport="stdio",
        environment={},
        workspace_id=str(identity["workspace_id"]),
        workspace_path=str(workspace_root.resolve()),
        workspace_selection="registered-visible-workspace",
        package_version=SANCHO_VERSION,
        workspace_schema_min=WORKSPACE_SCHEMA_MIN_READER,
        workspace_schema_max=WORKSPACE_SCHEMA_MAX_READER,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallStateError(f"Client configuration is unreadable or malformed: {path}") from exc
    if not isinstance(value, dict):
        raise InstallStateError(f"Client configuration must contain a JSON object: {path}")
    return value


def _mac_app_exists(name: str) -> bool:
    return (Path("/Applications") / name).exists() or (Path.home() / "Applications" / name).exists()


def _user_config_root() -> Path:
    system = platform.system()
    if system == "Windows":
        roaming = os.environ.get("APPDATA")
        return Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else Path.home() / ".config"


class ClientAdapter:
    name: str

    def detect(self) -> bool:
        raise NotImplementedError

    def inspect(self, launch: LaunchDefinition) -> ClientResult:
        raise NotImplementedError

    def apply(self, launch: LaunchDefinition, *, replace_unowned: bool = False) -> ClientResult:
        raise NotImplementedError

    def status(self, launch: LaunchDefinition) -> ClientResult:
        return self.inspect(launch)

    def repair(self, launch: LaunchDefinition, *, replace_unowned: bool = False) -> ClientResult:
        return self.apply(launch, replace_unowned=replace_unowned)

    def remove(self, launch: LaunchDefinition) -> ClientResult:
        raise NotImplementedError


class JsonClientAdapter(ClientAdapter):
    def __init__(
        self,
        name: str,
        config_path: Path,
        root_key: str,
        server_value: dict[str, Any],
        *,
        detected: bool,
        restart_required: bool = True,
        profile: str = "default",
        status_metadata: dict[str, Any] | None = None,
        pending_detail: str | None = None,
    ) -> None:
        self.name = name
        self.config_path = config_path
        self.root_key = root_key
        self.server_value = server_value
        self._detected = detected
        self._restart_required = restart_required
        self.profile = profile
        self.status_metadata = dict(status_metadata or {})
        self.pending_detail = pending_detail

    def detect(self) -> bool:
        return self._detected

    def _current(self) -> Any:
        config = _read_json_object(self.config_path)
        root = config.get(self.root_key, {})
        if not isinstance(root, dict):
            raise InstallStateError(
                f"{self.config_path} field {self.root_key!r} must contain an object"
            )
        return root.get("sancho")

    def inspect(self, launch: LaunchDefinition) -> ClientResult:
        try:
            state = load_install_state()
            if not self.detect():
                if isinstance(state["clients"].get(self.name), dict):
                    return ClientResult(
                        self.name,
                        "user_action_required",
                        "a recorded client/profile or its configuration is now absent",
                        detected=False,
                        user_action_required=True,
                    )
                return ClientResult(self.name, "absent", "client not detected", detected=False)
            current = self._current()
        except InstallStateError as exc:
            return ClientResult(self.name, "failed", str(exc), safe_retry="sancho doctor --fix")
        record = state["clients"].get(self.name)
        if current is None:
            return ClientResult(self.name, "user_action_required", "not configured", user_action_required=True)
        if not isinstance(record, dict):
            return ClientResult(
                self.name,
                "user_action_required",
                "a same-name unowned entry exists and was preserved",
                user_action_required=True,
            )
        if current != record.get("installed_value"):
            return ClientResult(
                self.name,
                "preserved_drift",
                "the Sancho-owned entry was edited; the current value was preserved",
                user_action_required=True,
            )
        if current != self.server_value:
            return ClientResult(self.name, "configured", "owned entry needs an update")
        state_name = "restart_required" if self._restart_required else "configured"
        return ClientResult(
            self.name,
            state_name,
            self.pending_detail
            or ("configuration matches; restart the client to load it" if self._restart_required else "configuration matches"),
            user_action_required=self._restart_required,
            metadata=self.status_metadata,
        )

    def apply(self, launch: LaunchDefinition, *, replace_unowned: bool = False) -> ClientResult:
        if not self.detect():
            return ClientResult(self.name, "absent", "client not detected", detected=False)
        try:
            # Validate ownership before touching a shared config. Missing is a
            # clean first install; corrupt/unreadable is a hard stop.
            state = load_install_state()
            with state_lock(self.config_path):
                config = _read_json_object(self.config_path)
                root = config.setdefault(self.root_key, {})
                if not isinstance(root, dict):
                    raise InstallStateError(
                        f"{self.config_path} field {self.root_key!r} must contain an object"
                    )
                current = root.get("sancho")
                record = state["clients"].get(self.name)
                if current is not None and not isinstance(record, dict) and not replace_unowned:
                    return ClientResult(
                        self.name,
                        "user_action_required",
                        "a same-name unowned entry exists and was preserved",
                        user_action_required=True,
                    )
                if (
                    current is not None
                    and isinstance(record, dict)
                    and current != record.get("installed_value")
                    and not replace_unowned
                ):
                    return ClientResult(
                        self.name,
                        "preserved_drift",
                        "the existing entry changed after Sancho wrote it; it was preserved",
                        user_action_required=True,
                    )
                changed = current != self.server_value
                if changed:
                    root["sancho"] = self.server_value
                    atomic_write_json(self.config_path, config, sort_keys=False)
            with state_lock():
                latest = load_install_state()
                bind_workspace(latest, Path(launch.workspace_path), read_workspace_identity(Path(launch.workspace_path)))
                latest["clients"][self.name] = {
                    "mechanism": "atomic-json-merge",
                    "config_path": str(self.config_path),
                    "root_key": self.root_key,
                    "installed_value": self.server_value,
                    "workspace_id": launch.workspace_id,
                    "package_version": launch.package_version,
                    "profile": self.profile,
                }
                save_install_state(latest)
        except (InstallStateError, OSError) as exc:
            return ClientResult(self.name, "failed", str(exc), safe_retry="sancho setup --client " + self.name)
        state_name = "restart_required" if self._restart_required else "configured"
        return ClientResult(
            self.name,
            state_name if changed else "unchanged",
            (
                self.pending_detail
                if self.pending_detail
                else "configured; restart required"
                if changed and self._restart_required
                else "configuration already matches; restart if the client has not loaded it"
                if self._restart_required
                else "configuration already matches"
            ),
            changed=changed,
            # Static configuration cannot prove that a proprietary GUI has
            # already reloaded, accepted trust, or passed organization policy.
            user_action_required=self._restart_required,
            metadata=self.status_metadata,
        )

    def remove(self, launch: LaunchDefinition) -> ClientResult:
        try:
            state = load_install_state(allow_missing=False)
            record = state["clients"].get(self.name)
            if not isinstance(record, dict):
                return ClientResult(self.name, "unchanged", "no Sancho-owned entry was recorded")
            with state_lock(self.config_path):
                config = _read_json_object(self.config_path)
                root = config.get(self.root_key, {})
                current = root.get("sancho") if isinstance(root, dict) else None
                if current is not None and current != record.get("installed_value"):
                    return ClientResult(
                        self.name,
                        "preserved_drift",
                        "edited entry was preserved",
                        user_action_required=True,
                    )
                changed = current is not None
                if changed:
                    del root["sancho"]
                    atomic_write_json(self.config_path, config, sort_keys=False)
            with state_lock():
                latest = load_install_state(allow_missing=False)
                latest["clients"].pop(self.name, None)
                save_install_state(latest)
            return ClientResult(self.name, "removed" if changed else "unchanged", "owned entry removed" if changed else "entry already absent", changed=changed)
        except (InstallStateError, OSError) as exc:
            return ClientResult(self.name, "failed", str(exc))


class CodexAdapter(ClientAdapter):
    name = "codex"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("codex")

    def detect(self) -> bool:
        # The binary can be on a developer/CI PATH even when the current user
        # has no Codex/ChatGPT profile.  Require the shared config home too.
        return bool(self.executable and (Path.home() / ".codex").exists())

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any] | None:
        transport = payload.get("transport")
        if not isinstance(transport, dict) or transport.get("type") != "stdio":
            return None
        return {
            "command": transport.get("command"),
            "args": transport.get("args") or [],
            "env": transport.get("env") or {},
        }

    def _get(self) -> tuple[dict[str, Any] | None, str | None]:
        if not self.executable:
            return None, None
        try:
            result = subprocess.run(
                [self.executable, "mcp", "get", "sancho", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, str(exc)
        if result.returncode != 0:
            # Only a definite "no such server" means absent. Any other failure
            # must fail closed: treating a transient error as "not configured"
            # would let remove() drop the ownership record while a live entry
            # survives in Codex.
            output = f"{result.stdout}\n{result.stderr}"
            if "No MCP server named" in output:
                return None, None
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            return None, f"`codex mcp get sancho` failed: {detail}"
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None, "Codex returned malformed JSON from `codex mcp get sancho --json`"
        if not isinstance(payload, dict):
            return None, "Codex returned an unexpected MCP configuration shape"
        return self._normalize(payload), None

    @staticmethod
    def _expected(launch: LaunchDefinition) -> dict[str, Any]:
        return {
            "command": launch.executable,
            "args": list(launch.arguments),
            "env": dict(launch.environment),
        }

    def _add(self, value: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        if not self.executable:
            raise OSError("Codex CLI is unavailable")
        command = [self.executable, "mcp", "add", "sancho"]
        environment = value.get("env") or {}
        if not isinstance(environment, dict):
            raise OSError("Codex MCP environment is not an object")
        for key, item in environment.items():
            command.extend(["--env", f"{key}={item}"])
        executable = value.get("command")
        arguments = value.get("args") or []
        if not isinstance(executable, str) or not isinstance(arguments, list):
            raise OSError("Codex MCP command is incomplete")
        command.extend(["--", executable, *(str(item) for item in arguments)])
        return subprocess.run(command, capture_output=True, text=True, timeout=15)

    def _remove(self) -> subprocess.CompletedProcess[str]:
        if not self.executable:
            raise OSError("Codex CLI is unavailable")
        return subprocess.run(
            [self.executable, "mcp", "remove", "sancho"],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def _restore(self, previous: dict[str, Any] | None) -> str:
        if previous is None:
            return "rollback not needed"
        try:
            restored = self._add(previous)
        except (OSError, subprocess.TimeoutExpired):
            return "previous registration could not be restored"
        return (
            "previous registration restored"
            if restored.returncode == 0
            else "previous registration could not be restored"
        )

    def inspect(self, launch: LaunchDefinition) -> ClientResult:
        try:
            state = load_install_state()
        except InstallStateError as exc:
            return ClientResult(self.name, "failed", str(exc))
        if not self.detect():
            recorded = isinstance(state["clients"].get(self.name), dict)
            return ClientResult(
                self.name,
                "user_action_required" if recorded else "absent",
                (
                    "a recorded Codex registration cannot be inspected because the CLI/profile is absent"
                    if recorded
                    else "Codex CLI not found; use ChatGPT/Codex Settings → MCP servers → Add server"
                ),
                detected=False,
                user_action_required=recorded,
            )
        current, error = self._get()
        if error:
            return ClientResult(self.name, "failed", error)
        if current is None:
            return ClientResult(self.name, "user_action_required", "not configured", user_action_required=True)
        record = state["clients"].get(self.name)
        if not isinstance(record, dict):
            return ClientResult(self.name, "user_action_required", "unowned same-name Codex entry was preserved", user_action_required=True)
        if current != record.get("installed_value"):
            return ClientResult(self.name, "preserved_drift", "Codex entry was edited and preserved", user_action_required=True)
        if current != self._expected(launch):
            return ClientResult(self.name, "configured", "owned Codex entry needs an update")
        return ClientResult(self.name, "configured", "Codex MCP registration matches")

    def apply(self, launch: LaunchDefinition, *, replace_unowned: bool = False) -> ClientResult:
        if not self.detect() or not self.executable:
            return self.inspect(launch)
        try:
            state = load_install_state()
        except InstallStateError as exc:
            return ClientResult(self.name, "failed", str(exc))
        current, error = self._get()
        if error:
            return ClientResult(self.name, "failed", error)
        record = state["clients"].get(self.name)
        if current is not None and not isinstance(record, dict) and not replace_unowned:
            return ClientResult(self.name, "user_action_required", "unowned same-name Codex entry was preserved", user_action_required=True)
        if current is not None and isinstance(record, dict) and current != record.get("installed_value") and not replace_unowned:
            return ClientResult(self.name, "preserved_drift", "edited Codex entry was preserved", user_action_required=True)
        expected = self._expected(launch)
        changed = current != expected
        if changed:
            # Codex exposes no atomic update command. Remove only after the
            # current value passes the ownership check above, then restore it
            # if the replacement add fails for any reason.
            try:
                if current is not None:
                    removed = self._remove()
                    if removed.returncode != 0:
                        detail = removed.stderr.strip() or removed.stdout.strip() or "unknown error"
                        return ClientResult(self.name, "failed", f"Codex MCP remove-before-update failed: {detail}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                return ClientResult(self.name, "failed", f"Codex MCP remove-before-update failed: {exc}")
            try:
                result = self._add(expected)
            except (OSError, subprocess.TimeoutExpired) as exc:
                rollback = self._restore(current)
                return ClientResult(self.name, "failed", f"Codex MCP add failed: {exc}; {rollback}")
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                rollback = self._restore(current)
                return ClientResult(self.name, "failed", f"Codex MCP add failed: {detail}; {rollback}")
        verified, error = self._get()
        if error or verified != expected:
            return ClientResult(self.name, "failed", error or "Codex did not retain the expected MCP registration")
        try:
            with state_lock():
                latest = load_install_state()
                bind_workspace(latest, Path(launch.workspace_path), read_workspace_identity(Path(launch.workspace_path)))
                latest["clients"][self.name] = {
                    "mechanism": "codex-cli",
                    "installed_value": expected,
                    "workspace_id": launch.workspace_id,
                    "package_version": launch.package_version,
                }
                save_install_state(latest)
        except InstallStateError as exc:
            return ClientResult(self.name, "failed", str(exc))
        return ClientResult(self.name, "configured" if changed else "unchanged", "Codex MCP registration verified", changed=changed)

    def remove(self, launch: LaunchDefinition) -> ClientResult:
        try:
            state = load_install_state(allow_missing=False)
        except InstallStateError as exc:
            return ClientResult(self.name, "failed", str(exc))
        record = state["clients"].get(self.name)
        if not isinstance(record, dict):
            return ClientResult(self.name, "unchanged", "no Sancho-owned Codex entry was recorded")
        if not self.detect() or not self.executable:
            return ClientResult(
                self.name,
                "user_action_required",
                "the recorded Codex entry could not be inspected or removed because the Codex CLI/profile is absent",
                detected=False,
                user_action_required=True,
                safe_retry="Restore the Codex CLI/profile, then rerun `sancho uninstall`.",
            )
        current, error = self._get()
        if error:
            return ClientResult(self.name, "failed", error)
        if current is not None and current != record.get("installed_value"):
            return ClientResult(self.name, "preserved_drift", "edited Codex entry was preserved", user_action_required=True)
        changed = current is not None
        if changed:
            try:
                result = self._remove()
            except (OSError, subprocess.TimeoutExpired) as exc:
                return ClientResult(self.name, "failed", f"Codex MCP remove failed: {exc}")
            if result.returncode != 0:
                return ClientResult(self.name, "failed", result.stderr.strip() or "Codex MCP remove failed")
        try:
            with state_lock():
                latest = load_install_state(allow_missing=False)
                latest["clients"].pop(self.name, None)
                save_install_state(latest)
        except InstallStateError as exc:
            return ClientResult(self.name, "failed", str(exc))
        return ClientResult(self.name, "removed" if changed else "unchanged", "Codex entry removed through Codex CLI" if changed else "entry already absent", changed=changed)


def _client_detected(name: str, config_path: Path) -> bool:
    if config_path.exists():
        return True
    if name == "claude-desktop":
        system = platform.system()
        if system == "Darwin":
            return _mac_app_exists("Claude.app")
        if system == "Windows":
            # Claude Code also exposes a `claude` command, so PATH is not
            # evidence that the Desktop app is installed. Its per-user
            # application config directory is a narrower Windows signal.
            return config_path.parent.exists()
        return False
    if name == "cursor":
        return _mac_app_exists("Cursor.app") or bool(shutil.which("cursor"))
    if name == "vscode":
        return _mac_app_exists("Visual Studio Code.app") or bool(shutil.which("code"))
    return False


def client_adapters(
    launch: LaunchDefinition,
    *,
    vscode_config_path: Path | None = None,
) -> dict[str, ClientAdapter]:
    root = _user_config_root()
    claude_path = root / "Claude" / "claude_desktop_config.json"
    vscode_path = root / "Code" / "User" / "mcp.json"
    vscode_profile = "default"
    if vscode_config_path is not None:
        requested = vscode_config_path.expanduser()
        vscode_path = requested if requested.suffix.lower() == ".json" else requested / "mcp.json"
        vscode_profile = str(vscode_path.resolve())
    cursor_path = Path.home() / ".cursor" / "mcp.json"
    adapters: dict[str, ClientAdapter] = {
        "claude-desktop": JsonClientAdapter(
            "claude-desktop",
            claude_path,
            "mcpServers",
            launch.stdio_server(),
            detected=_client_detected("claude-desktop", claude_path),
        ),
        "codex": CodexAdapter(),
        "cursor": JsonClientAdapter(
            "cursor",
            cursor_path,
            "mcpServers",
            launch.stdio_server(include_type=True),
            detected=_client_detected("cursor", cursor_path),
        ),
        "vscode": JsonClientAdapter(
            "vscode",
            vscode_path,
            "servers",
            launch.stdio_server(include_type=True),
            detected=_client_detected("vscode", vscode_path),
            profile=vscode_profile,
            pending_detail=(
                "configuration matches this profile; VS Code must confirm trust and may still require Copilot sign-in or organization-policy approval"
            ),
            status_metadata={
                "profile": vscode_profile,
                "trust": "client_confirmation_required_before_first_launch",
                "copilot_sign_in": "not_observable_from_configuration",
                "organization_policy": "not_observable_from_configuration",
                "remote_host": "local_profile_only",
                "removal": "automatic_only_while_the_recorded_config_value_matches",
            },
        ),
    }
    return adapters


def direct_stdio_handshake(launch: LaunchDefinition) -> ClientResult:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "sancho-setup", "version": SANCHO_VERSION},
        },
    }
    try:
        result = subprocess.run(
            [launch.executable, *launch.arguments],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ClientResult("sancho-mcp", "failed", f"direct stdio launch failed: {exc}")
    if result.returncode != 0:
        return ClientResult(
            "sancho-mcp",
            "failed",
            f"direct stdio launch failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    first = next((line for line in result.stdout.splitlines() if line.strip()), "")
    try:
        payload = json.loads(first)
    except json.JSONDecodeError:
        return ClientResult("sancho-mcp", "failed", "direct stdio launch returned malformed JSON")
    if not isinstance(payload, dict) or payload.get("id") != 1 or "result" not in payload:
        return ClientResult("sancho-mcp", "failed", "direct stdio handshake did not return an initialize result")
    return ClientResult("sancho-mcp", "launch_verified", "direct stdio initialize handshake passed")
