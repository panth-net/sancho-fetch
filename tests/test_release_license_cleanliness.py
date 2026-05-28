"""Release-gate test: ensure old custom-license language does not leak back in.

Sancho Fetch transitioned from the Sancho Fetch Fair Community License 1.0 to
Apache License 2.0 for code and CC BY 4.0 for docs. This test fails if any of
the public-facing files reintroduce strings tied to the retired custom license
(commercial threshold, white-label restrictions, paid-license gating, etc.).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.release_gate


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_LICENSE_STRINGS = [
    "Fair Community License",
    "fair-use community license",
    "public-source software",
    "Community Threshold",
    "Commercial License",
    "commercial license is required",
    "paid license",
    "white-label resale",
    "hosted resale",
    "USD $2,000,000",
]

PUBLIC_PATHS = [
    "LICENSE",
    "NOTICE",
    "README.md",
    "README_ALL_INSTRUCTIONS.md",
    "LICENSE-DOCS.md",
    "npm-cli/LICENSE",
    "npm-cli/NOTICE",
    "npm-cli/README.md",
    "npm-cli/package.json",
    "pyproject.toml",
]


@pytest.mark.parametrize("relative_path", PUBLIC_PATHS)
def test_no_old_license_language(relative_path: str) -> None:
    path = ROOT / relative_path
    assert path.exists(), f"expected public file is missing: {relative_path}"
    text = path.read_text(encoding="utf-8")
    offenders = [s for s in FORBIDDEN_LICENSE_STRINGS if s.lower() in text.lower()]
    assert not offenders, (
        f"{relative_path} contains retired license language: {offenders}"
    )
