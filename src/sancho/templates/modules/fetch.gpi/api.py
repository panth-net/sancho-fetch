from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from sancho.runtime.net import download_file

_PDF_URL_TEMPLATE = "https://www.economicsandpeace.org/wp-content/uploads/{year}/06/GPI-{year}-web.pdf"
_PROBE_YEARS_BACK = 5


def build_source_url(*, year: int | None) -> str:
    if year:
        return _PDF_URL_TEMPLATE.format(year=year)
    return _PDF_URL_TEMPLATE.format(year=datetime.now(timezone.utc).year)


def _discover_latest_year(timeout: int = 15) -> int:
    current_year = datetime.now(timezone.utc).year
    for y in range(current_year, current_year - _PROBE_YEARS_BACK, -1):
        url = _PDF_URL_TEMPLATE.format(year=y)
        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True)
            if resp.status_code < 400:
                return y
        except requests.RequestException:
            continue
    raise RuntimeError(
        f"Could not locate a GPI PDF for any year in "
        f"[{current_year - _PROBE_YEARS_BACK + 1}..{current_year}]."
    )


def fetch_gpi(
    *,
    runtime_http: dict[str, Any],
    dest_dir: Path,
    year: int | None,
    country: str | None,
) -> dict[str, Any]:
    timeout = float(runtime_http.get("timeout_seconds", 60))
    resolved_year = year if year is not None else _discover_latest_year(timeout=int(timeout))
    source_url = _PDF_URL_TEMPLATE.format(year=resolved_year)

    result = download_file(
        source_url,
        dest_dir=dest_dir,
        filename=f"GPI-{resolved_year}-web.pdf",
        expected_magic=b"%PDF",
        timeout=timeout,
    )

    return {
        "source_url": source_url,
        "pdf_path": str(result.path),
        "format": result.detected_format,
        "size_bytes": result.size_bytes,
        "year": resolved_year,
        "rows": [],
        "row_count": 0,
    }
