from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any

import requests


URL_TEMPLATE = "https://hdr.undp.org/sites/default/files/{year}_HDR/HDR{short_year}_Composite_indices_complete_time_series.csv"
META_COLUMNS = {"iso3", "country", "hdicode", "region"}


def build_source_url(*, year: int | None) -> str:
    effective_year = year or _discover_latest_year()
    short_year = str(effective_year)[2:]
    return URL_TEMPLATE.format(year=effective_year, short_year=short_year)


def _discover_latest_year() -> int:
    current_year = datetime.now().year
    for candidate in range(current_year, current_year - 12, -1):
        url = URL_TEMPLATE.format(year=candidate, short_year=str(candidate)[2:])
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return candidate
        except requests.RequestException:
            continue
    return 2024


def _parse_metric_col(col_name: str) -> tuple[str, int | None]:
    match = re.search(r"(\d{4})$", col_name)
    if match:
        metric = col_name[: match.start()].strip("_ ")
        return metric, int(match.group(1))
    return col_name, None


def fetch_hdr(
    *,
    runtime_http: dict[str, Any],
    year: int | None,
    country: str | None,
    indicator: str | None,
) -> dict[str, Any]:
    url = build_source_url(year=year)
    timeout = float(runtime_http.get("timeout_seconds", 60))
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    for encoding in ("utf-8", "latin-1"):
        try:
            text = resp.content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = resp.content.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])
    rows: list[dict[str, Any]] = []

    for record in reader:
        iso3 = str(record.get("iso3", "")).strip().upper()
        if country and iso3 != country:
            continue
        for col in fieldnames:
            if col.lower() in META_COLUMNS:
                continue
            metric_name, obs_year = _parse_metric_col(col)
            if indicator and metric_name != indicator:
                continue
            value_str = str(record.get(col, "")).strip()
            if not value_str or value_str == "..":
                continue
            try:
                value = float(value_str)
            except ValueError:
                value = value_str
            rows.append({
                "country_iso3": iso3,
                "country_name": record.get("country", ""),
                "indicator": metric_name,
                "year": obs_year,
                "value": value,
            })

    return {"source_url": url, "rows": rows, "row_count": len(rows)}
