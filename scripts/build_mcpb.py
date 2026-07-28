"""Rebuild the committed Claude Desktop bundle (integrations/claude-desktop/sancho.mcpb).

An .mcpb is just a zip of the bundle folder (manifest.json + server/**).
Run this after changing either source file; tests/test_mcpb_bundle.py fails
until the committed bundle matches the sources. Deterministic (fixed
timestamps) so rebuilding without changes produces an identical file.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "integrations" / "claude-desktop"
OUTPUT = BUNDLE_DIR / "sancho.mcpb"
MEMBERS = ("manifest.json", "server/index.js")
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
