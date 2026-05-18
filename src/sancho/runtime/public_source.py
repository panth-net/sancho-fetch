from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

from sancho.runtime.contracts import ModuleContext
from sancho.runtime.http import HttpClient
from sancho.runtime.transform_rows import extract_rows


LINK_RE = re.compile(
    r"<a\b[^>]*?href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
    flags=re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")


def _clean_label(value: str) -> str:
    no_tags = TAG_RE.sub(" ", value)
    return " ".join(unescape(no_tags).split())


def _extract_links(
    *,
    html: str,
    base_url: str,
    search: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    needle = search.lower().strip() if search else ""
    seen: set[str] = set()
    for match in LINK_RE.finditer(html):
        href = unescape(match.group("href")).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        url = urljoin(base_url, href)
        label = _clean_label(match.group("label")) or url
        haystack = f"{label} {url}".lower()
        if needle and needle not in haystack:
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append({"title": label, "url": url})
        if len(rows) >= limit:
            break
    return rows


def _fetch_text(*, endpoint: str, params: dict[str, Any], runtime_http: dict[str, Any]) -> str:
    timeout = float(runtime_http.get("timeout_seconds", 60))
    headers = {
        "User-Agent": runtime_http.get("user_agent", "Mozilla/5.0 (sancho-fetch)")
    }
    response = requests.get(endpoint, params=params, headers=headers, timeout=timeout)
    if response.status_code == 403 and response.text:
        # Some public research portals block automated clients but still return
        # a useful public HTML body. Treat that as a page response instead of
        # misclassifying it as a credentialed API failure.
        return response.text
    response.raise_for_status()
    return response.text


def run_public_source(
    *,
    context: ModuleContext,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    endpoint = str(payload.get("endpoint") or config["default_endpoint"])
    params_obj = payload.get("params", config.get("default_params", {}))
    params = params_obj if isinstance(params_obj, dict) else {}
    mode = str(payload.get("mode") or config.get("default_mode", "json")).strip().lower()
    search_obj = payload.get("search", config.get("default_search"))
    search = str(search_obj) if search_obj is not None else None
    limit = int(payload.get("limit") or config.get("default_limit", 25))
    runtime_http = context.runtime.get("http", {})

    if mode == "html_links":
        raw_text = _fetch_text(endpoint=endpoint, params=params, runtime_http=runtime_http)
        rows = _extract_links(
            html=raw_text,
            base_url=endpoint,
            search=search,
            limit=limit,
        )
        if not rows and search:
            rows = _extract_links(
                html=raw_text,
                base_url=endpoint,
                search=None,
                limit=limit,
            )
        if not rows:
            rows = [{"title": config.get("source_title", "Official source page"), "url": endpoint}]
        raw: Any = {
            "content_type": "html",
            "source_url": endpoint,
            "link_count": len(rows),
            "search": search,
        }
    else:
        client = HttpClient(**runtime_http)
        raw = client.request_json("GET", endpoint, params=params)
        rows = extract_rows(
            raw,
            preferred_keys=tuple(config.get("preferred_keys", ("data", "results", "items", "features", "dataset"))),
        )
        if rows and isinstance(rows[0], dict) and isinstance(rows[0].get("attributes"), dict):
            rows = [row["attributes"] for row in rows if isinstance(row, dict)]
        if not rows and isinstance(raw, dict):
            rows = [raw]
        rows = rows[:limit]

    return {
        "dataset_ref": config["dataset_ref"],
        "endpoint": endpoint,
        "params": params,
        "mode": mode,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
