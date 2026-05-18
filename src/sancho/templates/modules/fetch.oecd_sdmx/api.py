from __future__ import annotations

import csv
import io
from typing import Any

import requests

# ---------------------------------------------------------------------------
# SDMX CSV export endpoint
# ---------------------------------------------------------------------------

_SDMX_URL = (
    "https://sdmx.oecd.org/public/rest/data/"
    "{agency},{flow},{version}/all"
    "?format=csvfilewithlabels&dimensionAtObservation=AllDimensions"
)

_KNOWN_FLOWS: dict[str, tuple[str, str, str]] = {
    "current_wellbeing": ("OECD.WISE.CWB", "DSD_CWB@DF_CWB", "1.0"),
    "child_wellbeing": ("OECD.WISE.CWB", "DSD_CWB@DF_CWB", "1.0"),
    "future_wellbeing": ("OECD.WISE.CWB", "DSD_CWB@DF_CWB", "1.0"),
    "BLI": ("OECD", "BLI", "1.0"),
    "QNA": ("OECD", "QNA", "1.0"),
}

# Columns that may contain the country identifier in SDMX CSV exports.
_COUNTRY_COLUMNS = ("Country", "REF_AREA")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_source_url(*, dataset: str) -> str:
    """Return the SDMX CSV download URL for *dataset*."""
    if dataset in _KNOWN_FLOWS:
        agency, flow, version = _KNOWN_FLOWS[dataset]
    else:
        agency, flow, version = "OECD", dataset, "1.0"
    return _SDMX_URL.format(agency=agency, flow=flow, version=version)


def fetch_oecd_sdmx(
    *,
    runtime_http: dict[str, Any],
    dataset: str,
    country: str | None = None,
) -> dict[str, Any]:
    """Download an OECD SDMX CSV dataset and return parsed rows.

    Parameters
    ----------
    runtime_http:
        HTTP configuration from the Sancho Fetch runtime (e.g. ``timeout_seconds``).
    dataset:
        One of the known flow identifiers (``current_wellbeing``,
        ``child_wellbeing``, ``future_wellbeing``) or any valid SDMX
        dataflow id.
    country:
        Optional country filter.  Matched against the ``Country`` or
        ``REF_AREA`` column (case-insensitive).

    Returns
    -------
    dict with ``source_url``, ``dataset``, ``rows``, and ``row_count``.
    """
    timeout = float(runtime_http.get("timeout_seconds", 60))
    url = build_source_url(dataset=dataset)

    resp = requests.get(
        url,
        headers={
            "User-Agent": "SanchoFetch/1.0 (sancho)",
            "Accept": "text/csv",
        },
        timeout=timeout,
    )
    resp.raise_for_status()

    rows = _parse_csv(resp.content, country=country)

    return {
        "source_url": url,
        "dataset": dataset,
        "rows": rows,
        "row_count": len(rows),
    }


# ---------------------------------------------------------------------------
# Internal CSV parsing
# ---------------------------------------------------------------------------


def _parse_csv(
    raw_bytes: bytes,
    *,
    country: str | None = None,
) -> list[dict[str, Any]]:
    """Parse comma-delimited CSV with labels and optionally filter by country."""
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    # Determine which column holds the country identifier.
    fieldnames = reader.fieldnames or []
    country_col: str | None = None
    for candidate in _COUNTRY_COLUMNS:
        if candidate in fieldnames:
            country_col = candidate
            break

    rows: list[dict[str, Any]] = []
    country_upper = country.upper() if country else None

    for record in reader:
        if country_upper and country_col:
            value = (record.get(country_col) or "").strip().upper()
            if value != country_upper:
                continue
        rows.append(dict(record))

    return rows
