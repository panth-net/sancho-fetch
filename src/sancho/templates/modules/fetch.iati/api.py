from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient

# ---------------------------------------------------------------------------
# IATI Datastore bulk-data endpoints (public, no auth required).
# ---------------------------------------------------------------------------

DATASETS_URL = "https://bulk-data.iatistandard.org/datasets-minimal"
REPORTING_ORGS_URL = "https://bulk-data.iatistandard.org/reporting-orgs"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_source_url() -> str:
    """Return the primary source URL for provenance tracking."""
    return DATASETS_URL


def fetch_iati(
    runtime_http: dict[str, Any],
    reporting_org: str | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    """Fetch IATI dataset manifest and reporting-org metadata.

    1. GET datasets-minimal  -> JSON with ``datasets`` array.
    2. GET reporting-orgs    -> JSON with ``reporting_orgs`` array.
    3. Join datasets with their reporting-org names.
    4. Filter by *reporting_org* identifier if provided.
    5. Apply *limit*.
    """
    client = HttpClient(**runtime_http)

    # -- Fetch datasets manifest ----------------------------------------
    datasets_payload = client.request_json("GET", DATASETS_URL)
    datasets: list[dict[str, Any]] = (
        datasets_payload.get("datasets", [])
        if isinstance(datasets_payload, dict)
        else []
    )

    # -- Fetch reporting-orgs -------------------------------------------
    orgs_payload = client.request_json("GET", REPORTING_ORGS_URL)
    reporting_orgs: list[dict[str, Any]] = (
        orgs_payload.get("reporting_orgs", [])
        if isinstance(orgs_payload, dict)
        else []
    )

    # -- Build lookup: org identifier -> org name -----------------------
    org_name_map: dict[str, str] = {}
    for org in reporting_orgs:
        org_id = org.get("org_id") or org.get("identifier") or ""
        org_name = org.get("org_name") or org.get("name") or ""
        if org_id:
            org_name_map[str(org_id)] = str(org_name)

    # -- Join datasets with org names -----------------------------------
    for ds in datasets:
        ds_org = ds.get("reporting_org_ref") or ds.get("reporting_org") or ""
        ds["reporting_org_name"] = org_name_map.get(str(ds_org), "")

    # -- Filter by reporting_org if provided ----------------------------
    if reporting_org:
        match_val = reporting_org.upper()
        datasets = [
            ds
            for ds in datasets
            if match_val
            in (
                str(
                    ds.get("reporting_org_ref")
                    or ds.get("reporting_org")
                    or ""
                )
                .upper()
            )
        ]

    # -- Limit results --------------------------------------------------
    datasets = datasets[:limit]

    return {
        "source_url": DATASETS_URL,
        "rows": datasets,
        "reporting_orgs": reporting_orgs,
        "row_count": len(datasets),
    }
