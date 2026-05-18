"""Remove local generated artifacts before zipping or publishing the repo folder."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR_NAMES = {"__pycache__", ".pytest_cache", "sancho-fetched-data"}
GENERATED_SUFFIXES = {".pyc", ".pyo"}


def _inside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return True


def clean() -> list[Path]:
    removed: list[Path] = []
    for path in ROOT.rglob("*"):
        if not _inside_root(path):
            continue
        if path.is_dir() and path.name in GENERATED_DIR_NAMES:
            shutil.rmtree(path)
            removed.append(path)
        elif path.is_file() and path.suffix in GENERATED_SUFFIXES:
            path.unlink()
            removed.append(path)
    return removed


def main() -> int:
    removed = clean()
    print(f"Removed {len(removed)} generated artifact(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
