from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


DISCOVERY_FILE = "discovery.py"


def is_provider_module_id(module_id: str) -> bool:
    parts = module_id.split(".")
    return len(parts) >= 2 and parts[0] == "fetch" and all(bool(part.strip()) for part in parts[1:])


def discovery_file_path(module_dir: Path) -> Path:
    return module_dir / DISCOVERY_FILE


def has_discovery_file(module_dir: Path) -> bool:
    return discovery_file_path(module_dir).exists()


def _load_discovery_module(module_dir: Path) -> Any:
    path = discovery_file_path(module_dir)
    if not path.exists():
        raise FileNotFoundError(f"Missing discovery.py at {path}")
    spec = importlib.util.spec_from_file_location(f"sancho_provider_discovery_{module_dir.name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import discovery module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_module_discovery(module_dir: Path, *, offline: bool = False) -> dict[str, Any]:
    module = _load_discovery_module(module_dir)
    discover = getattr(module, "discover", None)
    if discover is None:
        raise RuntimeError(f"discovery.py must define discover(*, module_dir, offline=False): {module_dir}")
    result = discover(module_dir=module_dir, offline=offline)
    if not isinstance(result, dict):
        raise RuntimeError(f"discover() must return a dict summary: {module_dir}")
    return result
