#!/usr/bin/env python3
"""Generate the provider support matrix from code.

Usage:
    python scripts/generate_support_matrix.py              # print to stdout
    python scripts/generate_support_matrix.py --write      # write to project-docs/SUPPORT_MATRIX.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sancho.module_packs import MODULE_PACKS  # noqa: E402
from sancho.mcp.hosted_allowlist import HOSTED_PROVIDERS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "src" / "sancho" / "templates" / "modules"

# Known key requirements / optional credentials.
# Keep this aligned with module behavior and live test gating.
MODULE_KEYS: dict[str, str] = {
    "fetch.airnow": "AIRNOW_API_KEY",
    "fetch.atus": "BLS_API_KEY (optional)",
    "fetch.bea.nipa_table": "BEA_API_KEY",
    "fetch.bls": "BLS_API_KEY (optional)",
    "fetch.census.acs_profile": "CENSUS_API_KEY",
    "fetch.college_scorecard.schools": "DATA_GOV_API_KEY",
    "fetch.congress.bills": "CONGRESS_API_KEY",
    "fetch.dol.osha_inspections": "DOL_API_KEY",
    "fetch.eia.series": "EIA_API_KEY",
    "fetch.epa.aqs_annual": "AQS_API_KEY + AQS_EMAIL",
    "fetch.fbi.crime": "DATA_GOV_API_KEY",
    "fetch.fda.drug_events": "DATA_GOV_API_KEY (optional)",
    "fetch.fec": "DATA_GOV_API_KEY",
    "fetch.fred.series": "FRED_API_KEY",
    "fetch.hud.fmr": "HUD_API_TOKEN",
    "fetch.noaa.cdo": "NOAA_API_TOKEN",
    "fetch.nrel.alt_fuel_stations": "DATA_GOV_API_KEY",
    "fetch.regulations.dockets": "DATA_GOV_API_KEY",
    "fetch.usda.fooddata_search": "DATA_GOV_API_KEY",
    "fetch.usda.quickstats": "USDA_NASS_API_KEY",
    "fetch.uspto.application": "USPTO_API_KEY",
    "fetch.nyc_open_data": "SODA_API_KEY_ID (optional)",
    "fetch.cdc": "SODA_API_KEY_ID (optional)",
    "fetch.socrata.dataset": "SODA_API_KEY_ID (optional)",
    "fetch.socrata.chicago_crimes": "SODA_API_KEY_ID (optional)",
    "fetch.socrata.la_crime": "SODA_API_KEY_ID (optional)",
    "fetch.socrata.sf_building_permits": "SODA_API_KEY_ID (optional)",
    "fetch.socrata.seattle_building_permits": "SODA_API_KEY_ID (optional)",
}


def _all_modules() -> list[str]:
    mods: set[str] = set()
    for child in TEMPLATE_ROOT.iterdir():
        if child.is_dir() and (child / "module.yaml").exists():
            if child.name.startswith("fetch."):
                mods.add(child.name)
    return sorted(mods)


def _packs_for(module_id: str) -> list[str]:
    return sorted(p for p, mods in MODULE_PACKS.items() if module_id in mods)


def generate() -> str:
    lines: list[str] = []
    lines.append("# Provider Support Matrix")
    lines.append("")
    lines.append("> **Status: AUTHORITATIVE** - Generated from code by `scripts/generate_support_matrix.py`.")
    lines.append("> Regenerate with: `python scripts/generate_support_matrix.py --write`")
    lines.append("")
    lines.append("| Module | Key required | Hosted | Packs |")
    lines.append("|---|---|---|---|")

    for mod in _all_modules():
        key = MODULE_KEYS.get(mod, "None")
        hosted = "Yes" if mod in HOSTED_PROVIDERS else "No"
        packs = ", ".join(f"`{p}`" for p in _packs_for(mod)) or "standalone"
        lines.append(f"| `{mod}` | {key} | {hosted} | {packs} |")

    lines.append("")
    lines.append(f"**Total fetch modules:** {len(_all_modules())}")
    lines.append(f"**Hosted providers:** {len(HOSTED_PROVIDERS)}")
    lines.append(f"**Total packs:** {len(MODULE_PACKS)}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    content = generate()
    if "--write" in sys.argv:
        out = ROOT / "project-docs" / "SUPPORT_MATRIX.md"
        out.write_text(content, encoding="utf-8")
        print(f"Written to {out}")
    else:
        print(content)
