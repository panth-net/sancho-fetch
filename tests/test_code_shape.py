from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.shape


MAX_FILE_LINES = 350


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_no_super_python_files_in_core() -> None:
    root = Path(__file__).resolve().parents[1]
    src_root = root / "src" / "sancho"

    offenders: list[tuple[str, int]] = []
    for path in src_root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("src/sancho/templates/"):
            continue
        lines = _line_count(path)
        if lines > MAX_FILE_LINES:
            offenders.append((rel, lines))

    assert not offenders, f"Super files found (>{MAX_FILE_LINES} lines): {offenders}"


def test_no_super_python_files_in_templates() -> None:
    root = Path(__file__).resolve().parents[1]
    template_root = root / "src" / "sancho" / "templates"

    offenders: list[tuple[str, int]] = []
    for path in template_root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        lines = _line_count(path)
        if lines > MAX_FILE_LINES:
            offenders.append((rel, lines))

    assert not offenders, f"Template super files found (>{MAX_FILE_LINES} lines): {offenders}"
