from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


BASE_URL = "https://api.worldbank.org/v2"


def fetch_wgi(
    *,
    runtime_http: dict[str, Any],
    indicators: list[str],
    country: str | None,
    year_min: int | None,
    year_max: int | None,
) -> dict[str, Any]:
    # Override timeout: World Bank API is intermittently slow (20s default isn't enough)
    http_config = {**runtime_http, "timeout_seconds": 60, "max_retries": 4}
    client = HttpClient(**http_config)
    country_seg = country if country else "all"

    query_params: dict[str, Any] = {"format": "json", "per_page": 20000}
    if year_min is not None and year_max is not None:
        query_params["date"] = f"{year_min}:{year_max}"
    elif year_min is not None:
        query_params["date"] = f"{year_min}:9999"
    elif year_max is not None:
        query_params["date"] = f"1900:{year_max}"

    series: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for indicator in indicators:
        url = f"{BASE_URL}/country/{country_seg}/indicator/{indicator}"
        payload = client.request_json("GET", url, params=query_params)
        series[indicator] = payload
        if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
            for obs in payload[1]:
                if not isinstance(obs, dict):
                    continue
                rows.append({
                    "indicator": indicator,
                    "country_iso3": obs.get("countryiso3code"),
                    "country_name": (obs.get("country") or {}).get("value"),
                    "year": obs.get("date"),
                    "value": obs.get("value"),
                })
    return {"series": series, "rows": rows, "row_count": len(rows)}
