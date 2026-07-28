from __future__ import annotations

import re
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Pew Research Center public catalog endpoints
# ---------------------------------------------------------------------------

CATALOG_URL = "https://www.pewresearch.org/datasets/"
GLOBAL_URL = "https://www.pewresearch.org/global/datasets/"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def build_source_url(*, page: int) -> str:
    return CATALOG_URL


# Match Pew's current WordPress / PRC design-system markup.
# Dataset cards use either:
#   <h3 class="prc-card__heading"><a href="/dataset/...">Title</a></h3>
#   <h2 class="prc-card__title"><a href="/dataset/...">Title</a></h2>
# Be lenient about heading level and extra classes.
_CARD_HEADING_RE = re.compile(
    r'<h[1-4][^>]*class="[^"]*prc-card__[^"]*"[^>]*>\s*'
    r'<a[^>]*href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)

# Fallback: any <a> with href containing /dataset/ followed by title text
_DATASET_LINK_RE = re.compile(
    r'<a[^>]*href="([^"]*/dataset/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)


def fetch_pew_catalog(
    *,
    runtime_http: dict[str, Any],
    search: str | None,
    page: int,
    limit: int,
) -> dict[str, Any]:
    """Fetch the Pew Research public dataset catalog (HTML scraping).

    This fetches the browsable catalog only. Downloading actual datasets
    requires Selenium browser automation and a Pew Research account.
    """
    timeout = float(runtime_http.get("timeout_seconds", 30))
    url = build_source_url(page=page)

    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": _BROWSER_UA},
        allow_redirects=True,
    )
    resp.raise_for_status()

    # Try current PRC design system markup first, fall back to generic dataset links
    entries = _CARD_HEADING_RE.findall(resp.text)
    if not entries:
        entries = _DATASET_LINK_RE.findall(resp.text)

    # Deduplicate by URL
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for entry_url, title in entries:
        if entry_url in seen:
            continue
        seen.add(entry_url)

        title_clean = re.sub(r"\s+", " ", title).strip()
        if not title_clean or not entry_url:
            continue
        if search and search.lower() not in title_clean.lower():
            continue
        full_url = entry_url
        if full_url.startswith("/"):
            full_url = "https://www.pewresearch.org" + full_url
        rows.append({
            "title": title_clean,
            "url": full_url,
            "source": "pewresearch.org",
        })
        if len(rows) >= limit:
            break

    return {
        "source_url": url,
        "page": page,
        "note": "Catalog browsing only. Downloading datasets requires Selenium + Pew account.",
        "rows": rows,
        "row_count": len(rows),
    }
