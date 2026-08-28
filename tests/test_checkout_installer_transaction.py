from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _fake_checkout(tmp_path: Path) -> tuple[Path, Path, Path]:
    checkout = tmp_path / "Checkout & previous tool"
    installers = checkout / "installers"
    fake_bin = tmp_path / "fake-bin"
    installers.mkdir(parents=True)
    fake_bin.mkdir()
    shutil.copy2(ROOT / "installers" / "setup.sh", installers / "setup.sh")
    (checkout / "pyproject.toml").write_text("[project]\nname='sancho-fetch'\n", encoding="utf-8")
    marker = tmp_path / "previous-sancho-still-runnable"
    marker.write_text("working", encoding="utf-8")
    return checkout, fake_bin, marker


def _run_installer(checkout: Path, fake_bin: Path, tmp_path: Path, mode: str) -> subprocess.CompletedProcess[str]:
    uv = fake_bin / "uv"
    uv.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$FAKE_UV_LOG"
if [ "$1" = "build" ]; then
  if [ "$FAKE_UV_MODE" = "build-fail" ]; then exit 42; fi
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--out-dir" ]; then shift; mkdir -p "$1"; touch "$1/sancho_fetch-0.3.0-py3-none-any.whl"; exit 0; fi
    shift
  done
fi
if [ "$1" = "tool" ] && [ "$2" = "install" ]; then
  if [ "$FAKE_UV_MODE" = "install-fail" ]; then exit 43; fi
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" > "$FAKE_SANCHO_LOG"\n' > "$FAKE_UV_BIN/sancho"
  chmod +x "$FAKE_UV_BIN/sancho"
  exit 0
fi
if [ "$1" = "tool" ] && [ "$2" = "dir" ] && [ "$3" = "--bin" ]; then
  printf '%s\n' "$FAKE_UV_BIN"
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": os.pathsep.join([str(fake_bin), "/usr/bin", "/bin"]),
            "HOME": str(tmp_path / "home"),
            "FAKE_UV_MODE": mode,
            "FAKE_UV_LOG": str(tmp_path / f"{mode}.log"),
            "FAKE_UV_BIN": str(fake_bin),
            "FAKE_SANCHO_LOG": str(tmp_path / f"{mode}-sancho.log"),
        }
    )
    return subprocess.run(
        ["bash", str(checkout / "installers" / "setup.sh")],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX checkout installer")
@pytest.mark.parametrize("mode", ["build-fail", "install-fail"])
def test_checkout_installer_failure_never_uninstalls_previous_tool(
    tmp_path: Path,
    mode: str,
) -> None:
    checkout, fake_bin, marker = _fake_checkout(tmp_path)
    result = _run_installer(checkout, fake_bin, tmp_path, mode)
    assert result.returncode != 0
    assert marker.read_text(encoding="utf-8") == "working"
    commands = (tmp_path / f"{mode}.log").read_text(encoding="utf-8")
    assert "tool uninstall" not in commands
    if mode == "build-fail":
        assert "tool install" not in commands
    else:
        assert "tool install --reinstall" in commands


@pytest.mark.skipif(os.name == "nt", reason="POSIX checkout installer")
@pytest.mark.parametrize("mode", ["success", "same-version"])
def test_checkout_installer_reinstalls_validated_wheel_then_targets_checkout(
    tmp_path: Path,
    mode: str,
) -> None:
    checkout, fake_bin, _ = _fake_checkout(tmp_path)
    result = _run_installer(checkout, fake_bin, tmp_path, mode)
    assert result.returncode == 0, result.stdout + result.stderr
    commands = (tmp_path / f"{mode}.log").read_text(encoding="utf-8")
    assert "build --wheel --out-dir" in commands
    assert "tool install --reinstall" in commands
    assert "tool uninstall" not in commands
    setup_args = (tmp_path / f"{mode}-sancho.log").read_text(encoding="utf-8")
    assert "setup --path" in setup_args
    assert str(checkout) in setup_args
    assert "--switch-workspace" in setup_args


@pytest.mark.skipif(os.name == "nt", reason="POSIX checkout installer")
def test_checkout_installer_collision_failure_keeps_existing_executable(tmp_path: Path) -> None:
    checkout, fake_bin, _ = _fake_checkout(tmp_path)
    existing = fake_bin / "sancho"
    existing.write_bytes(b"unrelated executable bytes\n")
    existing.chmod(0o755)
    result = _run_installer(checkout, fake_bin, tmp_path, "install-fail")
    assert result.returncode != 0
    assert existing.read_bytes() == b"unrelated executable bytes\n"
