"""Cross-platform installed-wheel setup/repair/uninstall retention gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _json(command: list[str], env: dict[str, str]) -> dict:
    result = _run(command, env)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {command}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if wheel.is_dir():
        wheels = sorted(wheel.glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected exactly one wheel under {wheel}, found {len(wheels)}")
        wheel = wheels[0]
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is required for the wheel lifecycle gate")

    with tempfile.TemporaryDirectory(prefix="sancho-wheel-lifecycle-") as raw_root:
        root = Path(raw_root)
        home = root / "Home & Unicode Ω"
        project = root / "Project (lifecycle)"
        tool_dir = root / "uv-tools"
        bin_dir = root / "bin"
        home.mkdir()
        project.mkdir()
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "UV_TOOL_DIR": str(tool_dir),
                "UV_TOOL_BIN_DIR": str(bin_dir),
                "PATH": os.pathsep.join([str(bin_dir), env.get("PATH", "")]),
            }
        )
        _run([uv, "tool", "install", "--force", str(wheel)], env)
        executable = bin_dir / ("sancho.exe" if os.name == "nt" else "sancho")
        setup = _json([str(executable), "setup", "--path", str(project), "--json"], env)
        if setup.get("has_failures"):
            raise RuntimeError(f"installed-wheel setup failed: {setup}")
        workspace = Path(str(setup["workspace_root"]))
        env_file = workspace / ".env"
        secret_bytes = b"LIFECYCLE_PRIVATE_SENTINEL=must-survive\n"
        env_file.write_bytes(secret_bytes)

        ready = _json([str(executable), "ready", "--workspace", str(project), "--json"], env)
        if not ready.get("ready"):
            raise RuntimeError(f"installed-wheel readiness failed: {ready}")

        damaged = workspace / "mcp" / "cursor.mcp.json"
        damaged.unlink()
        doctor = _json(
            [str(executable), "doctor", "--workspace", str(project), "--fix", "--json"],
            env,
        )
        if doctor.get("status") != "ok" or not damaged.exists():
            raise RuntimeError(f"doctor did not repair the owned snippet: {doctor}")

        uninstall = _json([str(executable), "uninstall", "--json"], env)
        if uninstall.get("status") == "failed":
            raise RuntimeError(f"uninstall failed: {uninstall}")
        if not workspace.exists() or env_file.read_bytes() != secret_bytes:
            raise RuntimeError("default uninstall changed or removed the data-bearing workspace")
        if uninstall.get("workspaces_removed"):
            raise RuntimeError("default uninstall reported a removed workspace")

        _run([uv, "tool", "uninstall", "sancho-fetch"], env)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "wheel": str(wheel),
                    "workspace_retained": True,
                    "env_retained": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
