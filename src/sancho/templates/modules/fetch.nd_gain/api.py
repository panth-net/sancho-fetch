from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Any

import requests


DOWNLOAD_PAGE_URL = "https://gain-new.crc.nd.edu/about/download"

CSV_PATHS_IN_ZIP: dict[str, str] = {
    "gain": "resources/gain/gain.csv",
    "vulnerability": "resources/vulnerability/vulnerability.csv",
    "readiness": "resources/readiness/readiness.csv",
}


def _find_zip_url(html: str) -> str:
    """Regex-find the resources-*.zip link from the download page HTML."""
    # Match both absolute and relative URLs
    pattern = r'(?:https?://[^"\'>\s]+|/[^"\'>\s]+)resources-[^"\'>\s]*\.zip'
    matches = re.findall(pattern, html)
    if not matches:
        raise RuntimeError(
            "Could not locate a resources-*.zip download link on the ND-GAIN page"
        )
    # Prefer the latest timestamp when multiple links exist.
    matches.sort()
    url = matches[-1]
    # Convert relative URLs to absolute
    if url.startswith("/"):
        url = "https://gain-new.crc.nd.edu" + url
    return url


def _download_zip(url: str, dest: Path, timeout: float) -> None:
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    with dest.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)


def _parse_wide_csv(
    zf: zipfile.ZipFile,
    csv_path: str,
    metric_name: str,
) -> list[dict[str, Any]]:
    """Parse a wide-format CSV (country rows, year columns) into long rows."""
    try:
        raw_bytes = zf.read(csv_path)
    except KeyError:
        return []
    text = io.StringIO(raw_bytes.decode("utf-8", errors="replace"))
    reader = csv.DictReader(text)
    fieldnames = reader.fieldnames or []

    # Identify year columns (purely numeric headers).
    year_cols = [c for c in fieldnames if c.strip().isdigit()]
    # The first non-year column is treated as the country/ISO3 identifier.
    iso3_col = next(
        (c for c in fieldnames if not c.strip().isdigit()),
        None,
    )
    if iso3_col is None:
        return []

    rows: list[dict[str, Any]] = []
    for record in reader:
        country_iso3 = str(record.get(iso3_col, "")).strip().upper()
        if not country_iso3:
            continue
        for yr in year_cols:
            val = record.get(yr, "")
            if val is None or str(val).strip() == "":
                continue
            try:
                value = float(val)
            except (TypeError, ValueError):
                continue
            rows.append({
                "country_iso3": country_iso3,
                "metric": metric_name,
                "year": int(yr.strip()),
                "value": value,
            })
    return rows


def fetch_nd_gain(
    *,
    runtime_http: dict[str, Any],
    archive_cache_dir: Path,
    country: str | None,
    metric: str | None,
) -> dict[str, Any]:
    """Fetch ND-GAIN data: download page -> ZIP -> extract CSVs -> unpivot."""
    timeout = float(runtime_http.get("timeout_seconds", 120))

    # Step 1: GET the download page to find the ZIP URL.
    page_resp = requests.get(DOWNLOAD_PAGE_URL, timeout=timeout)
    page_resp.raise_for_status()
    zip_url = _find_zip_url(page_resp.text)

    # Step 2: Download the ZIP (cache on disk like V-Dem).
    archive_cache_dir.mkdir(parents=True, exist_ok=True)
    zip_filename = zip_url.rsplit("/", 1)[-1]
    archive_path = archive_cache_dir / zip_filename

    if not archive_path.exists():
        _download_zip(zip_url, archive_path, timeout=timeout)

    # Step 3: Extract and unpivot the three CSVs.
    metrics_to_load = (
        {metric: CSV_PATHS_IN_ZIP[metric]}
        if metric and metric in CSV_PATHS_IN_ZIP
        else CSV_PATHS_IN_ZIP
    )

    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive_path) as zf:
        for metric_name, csv_path in metrics_to_load.items():
            rows.extend(_parse_wide_csv(zf, csv_path, metric_name))

    # Step 4: Filter by country if requested.
    if country:
        rows = [r for r in rows if r.get("country_iso3") == country]

    return {
        "source_url": zip_url,
        "archive_path": str(archive_path),
        "rows": rows,
        "row_count": len(rows),
    }
