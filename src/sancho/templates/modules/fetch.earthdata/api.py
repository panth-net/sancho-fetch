from __future__ import annotations

from typing import Any

import requests

_CMR_BASE = "https://cmr.earthdata.nasa.gov/search"
_UA = "SanchoFetch/1.0 (sancho)"


def search_collections(
    *,
    runtime_http: dict[str, Any],
    token: str | None,
    keyword: str | None,
    bbox: list[float] | None,
    temporal: str | None,
    provider: str | None,
    limit: int,
) -> dict[str, Any]:
    timeout = float(runtime_http.get("timeout_seconds", 60))
    url = f"{_CMR_BASE}/collections.json"
    headers: dict[str, str] = {"User-Agent": _UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params: dict[str, Any] = {"page_size": min(limit, 2000)}
    if keyword:
        params["keyword"] = keyword
    if bbox:
        params["bounding_box"] = ",".join(str(v) for v in bbox)
    if temporal:
        params["temporal"] = temporal
    if provider:
        params["provider"] = provider

    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    feed = data.get("feed", {}) if isinstance(data, dict) else {}
    entries = feed.get("entry", []) if isinstance(feed, dict) else []
    if not isinstance(entries, list):
        entries = [entries] if entries else []
    rows = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        platforms = entry.get("platforms", [])
        if isinstance(platforms, list):
            platform_names = [p.get("short_name", "") for p in platforms if isinstance(p, dict)]
        else:
            platform_names = []
        rows.append({
            "id": entry.get("id", ""),
            "short_name": entry.get("short_name", ""),
            "title": entry.get("title", ""),
            "summary": str(entry.get("summary", ""))[:300],
            "time_start": entry.get("time_start", ""),
            "time_end": entry.get("time_end", ""),
            "data_center": entry.get("data_center", ""),
            "platforms": platform_names,
        })

    hits = feed.get("hits", len(rows)) if isinstance(feed, dict) else len(rows)
    return {
        "source_url": url,
        "total_results": int(hits) if hits else len(rows),
        "rows": rows,
    }


def search_granules(
    *,
    runtime_http: dict[str, Any],
    token: str | None,
    collection_concept_id: str,
    bbox: list[float] | None,
    temporal: str | None,
    limit: int,
) -> dict[str, Any]:
    timeout = float(runtime_http.get("timeout_seconds", 60))
    url = f"{_CMR_BASE}/granules.json"
    headers: dict[str, str] = {"User-Agent": _UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params: dict[str, Any] = {
        "collection_concept_id": collection_concept_id,
        "page_size": min(limit, 2000),
    }
    if bbox:
        params["bounding_box"] = ",".join(str(v) for v in bbox)
    if temporal:
        params["temporal"] = temporal

    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    entries = data.get("feed", {}).get("entry", [])
    rows = []
    for entry in entries[:limit]:
        links = [lnk.get("href", "") for lnk in entry.get("links", []) if lnk.get("rel") == "http://esipfed.org/ns/fedsearch/1.1/data#"]
        rows.append({
            "id": entry.get("id", ""),
            "title": entry.get("title", ""),
            "time_start": entry.get("time_start", ""),
            "time_end": entry.get("time_end", ""),
            "granule_size": entry.get("granule_size", ""),
            "data_links": links[:5],
        })

    return {
        "source_url": url,
        "collection_concept_id": collection_concept_id,
        "total_results": int(data.get("feed", {}).get("hits", len(rows))),
        "rows": rows,
    }
