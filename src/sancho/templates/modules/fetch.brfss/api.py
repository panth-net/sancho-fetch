from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests


BASE_URL = "https://www.cdc.gov/brfss/annual_data/annual_data.html"

_KIND_PATTERNS: dict[str, re.Pattern[str]] = {
    # Recent BRFSS years ship XPT data inside ZIP wrappers (LLCP2021XPT.zip),
    # so accept both bare .xpt and `XPT.{zip,exe}` filename suffixes.
    "data_xpt": re.compile(r"\.xpt(\?|$)|xpt\.(zip|exe)", re.IGNORECASE),
    "data_ascii": re.compile(r"\.asc(\?|$)|\.dat(\?|$)|ascii|asc\.(zip|exe)", re.IGNORECASE),
    "codebook": re.compile(r"codebook", re.IGNORECASE),
    "questionnaire": re.compile(r"questionnaire|survey\s*instrument", re.IGNORECASE),
    "documentation": re.compile(r"overview|summary|documentation|readme", re.IGNORECASE),
}

_SIZE_HINT: dict[str, str] = {
    "data_xpt": "~100-300 MB",
    "data_ascii": "~100-400 MB",
    "codebook": "~1-5 MB",
    "questionnaire": "~1-5 MB",
    "documentation": "~0.5-2 MB",
}


def build_source_url(*, year: int | None) -> str:
    if year is not None:
        return f"https://www.cdc.gov/brfss/annual_data/annual_{year}.html"
    return BASE_URL


def _classify_link(href: str, text: str) -> str:
    """Classify a link into a file_kind category."""
    combined = f"{href} {text}"
    for kind, pattern in _KIND_PATTERNS.items():
        if pattern.search(combined):
            return kind
    return "other"


def _parse_links(html: str, page_url: str, year: int | None) -> list[dict[str, Any]]:
    """Extract download-relevant links from page HTML."""
    link_pattern = re.compile(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    files: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for match in link_pattern.finditer(html):
        href_raw = match.group(1).strip()
        link_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()

        if not href_raw or href_raw.startswith("#") or href_raw.startswith("mailto:"):
            continue

        abs_url = urljoin(page_url, href_raw)

        is_download = bool(
            re.search(r"\.(xpt|zip|exe|dat|asc|pdf|sas7bdat)(\?|$)", abs_url, re.IGNORECASE)
        )
        if not is_download:
            continue
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)

        kind = _classify_link(abs_url, link_text)
        name = abs_url.rsplit("/", 1)[-1].split("?")[0] if "/" in abs_url else abs_url

        files.append({
            "name": name,
            "url": abs_url,
            "file_kind": kind,
            "year": year,
            "estimated_size": _SIZE_HINT.get(kind, "unknown"),
            "link_text": link_text,
        })

    return files


def _filter_by_kind(
    files: list[dict[str, Any]], file_kind: str | None
) -> list[dict[str, Any]]:
    if file_kind is None:
        return files
    return [f for f in files if f["file_kind"] == file_kind]


def fetch_manifest(
    *,
    runtime_http: dict[str, Any],
    year: int | None,
    file_kind: str | None,
) -> dict[str, Any]:
    """Fetch the BRFSS annual data page and parse file manifest.

    Returns a dict with source_url, year, files list, rows, and row_count.
    This is a discovery/manifest module -- it does not download the large
    data files themselves.
    """
    source_url = build_source_url(year=year)
    timeout = runtime_http.get("timeout_seconds", 30)

    resp = requests.get(source_url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    resp.raise_for_status()
    html = resp.text

    all_files = _parse_links(html, source_url, year)
    files = _filter_by_kind(all_files, file_kind)

    rows = [
        {
            "name": f["name"],
            "url": f["url"],
            "file_kind": f["file_kind"],
            "year": f.get("year"),
            "estimated_size": f["estimated_size"],
        }
        for f in files
    ]

    return {
        "source_url": source_url,
        "year": year,
        "files": files,
        "rows": rows,
        "row_count": len(rows),
    }
