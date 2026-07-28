from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

import requests

URL_TEMPLATE = "https://rsf.org/sites/default/files/import_classement/{year}.csv"


def build_source_url(*, year: int | None) -> str:
    effective_year = year or _discover_latest_year()
    return URL_TEMPLATE.format(year=effective_year)


def _discover_latest_year() -> int:
    current_year = datetime.now().year
    for candidate in range(current_year, current_year - 30, -1):
        url = URL_TEMPLATE.format(year=candidate)
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return candidate
        except requests.RequestException:
            continue
    return 2024


def fetch_rsf(
    *,
    runtime_http: dict[str, Any],
    year: int | None,
    country: str | None,
) -> dict[str, Any]:
    url = build_source_url(year=year)
    timeout = float(runtime_http.get("timeout_seconds", 30))
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    # Try multiple encodings
    for encoding in ("utf-8", "latin-1"):
        try:
            text = resp.content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = resp.content.decode("utf-8", errors="replace")

    # Remove BOM if present
    text = text.lstrip("\ufeff")

    # Parse as semicolon-delimited CSV
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows: list[dict[str, Any]] = []
    for record in reader:
        # Try to find ISO3 column
        iso3 = ""
        for key in ("ISO3", "ISO", "iso3", "iso"):
            if key in record and record[key]:
                iso3 = str(record[key]).strip().upper()
                break

        if country and iso3 != country:
            continue

        row: dict[str, Any] = {"country_iso3": iso3}
        for key, val in record.items():
            if key and val is not None:
                clean_key = key.strip().lower().replace(" ", "_")
                row[clean_key] = val.strip() if isinstance(val, str) else val
        rows.append(row)

    return {"source_url": url, "rows": rows, "row_count": len(rows)}
