from __future__ import annotations

import csv
import io
import logging
from typing import Any
from urllib.parse import quote

import requests

from sancho.runtime.http import HttpClient

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OWID endpoints
# ---------------------------------------------------------------------------

_SEARCH_URL = "https://ourworldindata.org/api/search"
_GRAPHER_CSV_URL = "https://ourworldindata.org/grapher/{slug}.csv?v=1&csvType=full&useColumnShortNames=true"
_METADATA_URL = "https://ourworldindata.org/grapher/{slug}.metadata.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_charts(
    client: HttpClient,
    query: str,
    hits_per_page: int = 20,
) -> list[dict[str, Any]]:
    """Search OWID for charts matching *query*."""
    data = client.request_json(
        "GET",
        _SEARCH_URL,
        params={
            "q": query,
            "type": "charts",
            "page": "0",
            "hitsPerPage": str(hits_per_page),
        },
    )
    if isinstance(data, dict):
        return data.get("hits", data.get("charts", []))
    return []


def _download_csv(slug: str, timeout: int = 30) -> list[dict[str, str]]:
    """Download a chart's full CSV and parse it into row dicts."""
    url = _GRAPHER_CSV_URL.format(slug=quote(slug, safe=""))
    resp = requests.get(url, timeout=timeout)
    if resp.status_code == 403:
        log.warning("Chart %s returned 403 (non-redistributable); skipping CSV.", slug)
        return []
    resp.raise_for_status()
    text = resp.text
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _fetch_metadata(client: HttpClient, slug: str) -> dict[str, Any]:
    """Fetch the JSON metadata for a chart."""
    url = _METADATA_URL.format(slug=quote(slug, safe=""))
    try:
        return client.request_json("GET", url)
    except Exception:
        log.warning("Failed to fetch metadata for chart %s; continuing.", slug)
        return {}


def _fetch_single_chart(
    client: HttpClient,
    slug: str,
    timeout: int,
) -> dict[str, Any]:
    """Download CSV + metadata for one chart slug."""
    csv_rows = _download_csv(slug, timeout=timeout)
    metadata = _fetch_metadata(client, slug)
    title = metadata.get("chart", {}).get("title", slug) if metadata else slug
    return {
        "slug": slug,
        "title": title,
        "csv_rows": csv_rows,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_owid_charts(
    *,
    runtime_http: dict[str, Any],
    slug: str | None = None,
    search: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Fetch one or more OWID charts by slug or search query.

    Returns a dict with ``source_url``, ``charts``, ``rows``, and ``row_count``.
    """
    client = HttpClient(**runtime_http)
    timeout = int(runtime_http.get("timeout_seconds", 30))

    charts: list[dict[str, Any]] = []
    all_rows: list[dict[str, str]] = []

    if slug:
        chart = _fetch_single_chart(client, slug, timeout)
        charts.append(chart)
        all_rows.extend(chart["csv_rows"])
        source_url = _GRAPHER_CSV_URL.format(slug=quote(slug, safe=""))
    elif search:
        hits = _search_charts(client, search)
        slugs = []
        for hit in hits:
            s = hit.get("slug") or hit.get("chartSlug") or ""
            if isinstance(s, str) and s.strip() and s not in slugs:
                slugs.append(s)
            if len(slugs) >= limit:
                break

        for s in slugs:
            chart = _fetch_single_chart(client, s, timeout)
            charts.append(chart)
            all_rows.extend(chart["csv_rows"])

        source_url = _SEARCH_URL + "?q=" + quote(search, safe="")
    else:
        source_url = "https://ourworldindata.org"

    return {
        "source_url": source_url,
        "charts": charts,
        "rows": all_rows,
        "row_count": len(all_rows),
    }
