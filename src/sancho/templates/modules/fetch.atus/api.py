from __future__ import annotations

from typing import Any

import requests

# BLS Public Data API v2 -- official, stable, no scraping required.
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Representative ATUS Table A-1 series IDs (time-use summary averages).
DEFAULT_SERIES = [
    "TUU10101AA01000100",  # Total, all activities
    "TUU10101AA01005300",  # Eating and drinking
    "TUU10101AA01005600",  # Household activities
    "TUU10101AA01025600",  # Work and work-related activities
    "TUU10101AA01026600",  # Leisure and sports
]

_UA = "SanchoFetch/1.0 (sancho)"


def build_source_url(*, year: int | None) -> str:
    return BLS_API_URL


def fetch_atus(
    runtime_http: dict[str, Any],
    api_key: str | None = None,
    series_ids: list[str] | None = None,
    start_year: str = "2019",
    end_year: str = "2023",
) -> dict[str, Any]:
    """Fetch ATUS time-series data via the BLS Public Data API v2."""
    timeout = float(runtime_http.get("timeout_seconds", 30))
    ids = series_ids or DEFAULT_SERIES

    body: dict[str, Any] = {
        "seriesid": ids,
        "startyear": start_year,
        "endyear": end_year,
    }
    if api_key:
        body["registrationkey"] = api_key

    resp = requests.post(
        BLS_API_URL,
        json=body,
        headers={"User-Agent": _UA, "Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    rows: list[dict[str, Any]] = []
    for series in data.get("Results", {}).get("series", []):
        sid = series.get("seriesID", "")
        for obs in series.get("data", []):
            rows.append({
                "series_id": sid,
                "year": obs.get("year", ""),
                "period": obs.get("period", ""),
                "value": obs.get("value", ""),
                "footnotes": [f.get("text", "") for f in obs.get("footnotes", []) if f.get("text")],
            })

    return {
        "source_url": BLS_API_URL,
        "series_count": len(data.get("Results", {}).get("series", [])),
        "rows": rows,
        "row_count": len(rows),
    }
