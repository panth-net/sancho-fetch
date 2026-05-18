from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient

# ---------------------------------------------------------------------------
# OWID Datasette public API endpoints
# ---------------------------------------------------------------------------

# Use _shape=objects so rows come back as dicts instead of arrays.
CHARTS_URL = "https://datasette-public.owid.io/owid/charts.json?_size=1000&_shape=objects"
TAGS_URL = "https://datasette-public.owid.io/owid/tags.json?_size=1000&_shape=objects"
CHART_TAGS_URL = "https://datasette-public.owid.io/owid/chart_tags.json?_size=1000&_shape=objects"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _paginate(client: HttpClient, url: str, limit: int) -> list[dict[str, Any]]:
    """Fetch rows from a Datasette JSON endpoint, following next_url pagination."""
    collected: list[dict[str, Any]] = []
    current_url: str | None = url

    while current_url and len(collected) < limit:
        data = client.request_json("GET", current_url)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("rows", [])
        else:
            break
        if not rows:
            break
        collected.extend(rows)
        current_url = data.get("next_url") if isinstance(data, dict) else None

    return collected[:limit]


def _resolve_tag_chart_ids(
    client: HttpClient, tag_name: str,
) -> set[int]:
    """Return the set of chart IDs associated with a given tag name."""
    # Fetch all tags to find the matching tag ID. Datasette may return either
    # a plain list of rows OR a dict envelope {"rows": [...]}.
    tag_data = client.request_json("GET", TAGS_URL)
    if isinstance(tag_data, list):
        tag_rows = tag_data
    elif isinstance(tag_data, dict):
        tag_rows = tag_data.get("rows", [])
    else:
        tag_rows = []
    tag_name_lower = tag_name.lower()

    tag_id: int | None = None
    for row in tag_rows:
        name = row.get("name", "")
        if isinstance(name, str) and name.lower() == tag_name_lower:
            tag_id = row.get("id")
            break

    if tag_id is None:
        return set()

    # Fetch chart_tags and collect chart IDs matching the tag
    chart_tag_rows = _paginate(client, CHART_TAGS_URL, limit=50_000)
    return {
        row["chartId"]
        for row in chart_tag_rows
        if row.get("tagId") == tag_id and "chartId" in row
    }


# ---------------------------------------------------------------------------
# Public fetch entry point
# ---------------------------------------------------------------------------


def fetch_owid_catalog(
    runtime_http: dict[str, Any],
    search: str | None = None,
    tag: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Fetch OWID chart catalog rows, optionally filtered by search term or tag."""
    client = HttpClient(**runtime_http)

    # Fetch charts with pagination
    all_charts = _paginate(client, CHARTS_URL, limit=limit * 3 if (search or tag) else limit)

    # Apply search filter on chart title
    if search:
        search_lower = search.lower()
        all_charts = [
            row for row in all_charts
            if search_lower in str(row.get("title", "")).lower()
            or search_lower in str(row.get("slug", "")).lower()
        ]

    # Apply tag filter
    if tag:
        allowed_ids = _resolve_tag_chart_ids(client, tag)
        if allowed_ids:
            all_charts = [
                row for row in all_charts
                if row.get("id") in allowed_ids
            ]
        else:
            all_charts = []

    # Enforce limit
    rows = all_charts[:limit]

    return {
        "source_url": CHARTS_URL,
        "rows": rows,
        "row_count": len(rows),
    }
