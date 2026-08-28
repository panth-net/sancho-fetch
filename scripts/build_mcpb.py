"""Rebuild the committed Claude Desktop bundle (integrations/claude-desktop/sancho.mcpb).

An .mcpb is just a zip of the MEMBERS files below. Run this after changing any
of them; tests/test_mcpb_bundle.py fails until the committed bundle matches
the sources. Deterministic (fixed timestamps, fixed order) so rebuilding
without changes produces an identical file.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "integrations" / "claude-desktop"
OUTPUT = BUNDLE_DIR / "sancho.mcpb"
MEMBERS = (".mcpbignore", "manifest.json", "pyproject.toml", "src/server.py")
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def build() -> Path:
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for member in MEMBERS:
            info = zipfile.ZipInfo(member, date_time=FIXED_DATE)
            info.external_attr = 0o644 << 16
            bundle.writestr(info, (BUNDLE_DIR / member).read_bytes())
    return OUTPUT


if __name__ == "__main__":
    print(build())
