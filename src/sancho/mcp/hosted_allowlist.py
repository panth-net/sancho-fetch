"""Allowlist + link-only catalog for the hosted remote-MCP variant.

This module defines which Sancho Fetch fetch providers are safe to expose through a
public hosted MCP server (Mode C). It is imported only by the hosting wrapper
(`hosting/server.py`). Local and desktop users never load this.

Criteria for HOSTED_PROVIDERS inclusion:
1. No required API key, OR the key is free and the host can ship its own
   through environment variables.
2. No login / OAuth / paid tier.
3. No bulk-download-only sources. Those belong in LINK_ONLY instead.

LINK_ONLY entries describe datasets that are distributed as bulk file dumps
(ZIP, CSV, PDF). The hosted server should not try to proxy those; it returns
the canonical download URL and nudges the user to install Sancho Fetch locally for
automated ingest. LINK_ONLY tools are NOT currently auto-registered as virtual
tools -- the dispatcher in `tooling._handle_method` intercepts them by name if
they ever show up in a `tools/call`, and the dict is also used to document
intent for future virtual-tool registration.
"""

from __future__ import annotations


# Real module IDs (must match directory names in src/sancho/templates/modules/).
# A boot-time assertion in `hosting/server.py` verifies every ID resolves.
HOSTED_PROVIDERS: set[str] = {
    "fetch.world_bank",
    "fetch.treasury.fiscal_data",
    "fetch.usaspending.awards",
    "fetch.usgs.earthquakes",
    "fetch.fema.openfema",
    "fetch.federal_register.documents",
    "fetch.cms.data",
    "fetch.nhtsa.recalls",
    "fetch.sec.company_submissions",
    "fetch.fda.drug_events",
    "fetch.cfpb.complaints",
    "fetch.clinical_trials.studies",
    "fetch.college_scorecard.schools",
    "fetch.fdic.institutions",
    "fetch.census.acs_profile",
}


# Bulk-download sources. Keyed by the name a tool call might use.
# The dispatcher short-circuits any tools/call with a name in this dict and
# returns the link instead of executing a module.
LINK_ONLY: dict[str, dict[str, str]] = {
    "african_data_barometer": {
        "url": "https://www.africandatabarometer.org/downloads",
        "description": "Bulk CSV/XLSX download of the African Data Barometer.",
    },
    "world_values_survey": {
        "url": "https://www.worldvaluessurvey.org/WVSDocumentationWVL.jsp",
        "description": "Bulk microdata download (SPSS/Stata/CSV) from the World Values Survey.",
    },
}


__all__ = ["HOSTED_PROVIDERS", "LINK_ONLY"]
