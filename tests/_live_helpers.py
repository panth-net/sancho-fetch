"""Shared utilities for live integration tests.

Not a test file (underscore prefix). Provides workspace setup, skip gates,
and assertion helpers used by all test_live_*.py files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from sancho.cli import main
from sancho.runtime.executor import run_module

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ENV = _PROJECT_ROOT / ".env"

# Load project .env into os.environ once so require_env_key() works
_env_loaded = False


def _load_project_env() -> None:
    global _env_loaded
    if _env_loaded or not _PROJECT_ENV.exists():
        return
    for line in _PROJECT_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:
            os.environ[key] = value
    _env_loaded = True


def require_live_gate() -> None:
    if os.getenv("SANCHO_LIVE_GATE", "").strip() != "1":
        pytest.skip("Live gate disabled. Set SANCHO_LIVE_GATE=1 to run.")
    _load_project_env()


def require_env_key(name: str) -> None:
    require_live_gate()
    if not os.getenv(name, "").strip():
        pytest.skip(f"Set {name} env var to run this test.")


def init_workspace(tmp_path: Path) -> Path:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    ws = tmp_path / "sancho-workspace"
    # Copy project .env so run_module picks up API keys
    if _PROJECT_ENV.exists():
        shutil.copy2(_PROJECT_ENV, ws / ".env")
    return ws


def add_and_run(
    workspace: Path, module_id: str, payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert main(["add", module_id, "--workspace", str(workspace.parent)]) == 0
    result = run_module(workspace, module_id=module_id, input_payload=payload or {})
    assert result.status == "ok", f"{module_id} returned status={result.status}"
    return result.output


def assert_output_shape(out: dict[str, Any], *required_keys: str) -> None:
    for key in required_keys:
        assert key in out, f"Missing key '{key}' in output: {list(out.keys())}"


def assert_has_rows(out: dict[str, Any], *, min_rows: int = 1, key: str = "rows") -> None:
    rows = out.get(key)
    assert isinstance(rows, list), f"output['{key}'] is {type(rows).__name__}, expected list"
    assert len(rows) >= min_rows, f"output['{key}'] has {len(rows)} items, expected >= {min_rows}"


def assert_row_fields(out: dict[str, Any], fields: list[str], *, key: str = "rows") -> None:
    rows = out.get(key, [])
    assert rows, f"No rows to check fields against"
    first = rows[0]
    if isinstance(first, dict):
        for f in fields:
            assert f in first, f"Field '{f}' missing from first row: {list(first.keys())[:15]}"


def assert_raw_saved(workspace: Path, module_id: str) -> None:
    slug = module_id.replace(".", "_")
    raw_dir = workspace / "data" / "raw" / slug
    if not raw_dir.exists():
        # Some modules use the module_id directly as directory name
        raw_dir = workspace / "data" / "raw" / module_id
    if not raw_dir.exists():
        return  # stateless mode or module doesn't use save_raw
    json_files = list(raw_dir.rglob("*.json"))
    meta_files = list(raw_dir.rglob("*.meta.json"))
    assert len(json_files) > 0, f"No .json files in {raw_dir}"
    assert len(meta_files) > 0, f"No .meta.json files in {raw_dir}"
