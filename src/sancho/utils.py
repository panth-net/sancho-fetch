from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# libyaml is ~5-10x faster than the pure-Python loader and just as safe;
# fall back when the wheel was built without it.
_YAML_SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_yaml(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    raw = path.read_text(encoding="utf-8")
    data = yaml.load(raw, Loader=_YAML_SAFE_LOADER)
    if data is None:
        return {} if default is None else default
    return data


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
