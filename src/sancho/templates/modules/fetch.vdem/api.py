from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

import requests


BASE_URL_TEMPLATE = "https://www.v-dem.net/media/datasets/V-Dem-CY-Core-v{version}_csv.zip"
CORE_META_COLUMNS = {"country_name", "country_text_id", "country_id", "year", "historical_date"}


def build_source_url(*, version: str) -> str:
    return BASE_URL_TEMPLATE.format(version=version)


def fetch_vdem_core(
    *,
    runtime_http: dict[str, Any],
    archive_cache_dir: Path,
    version: str,
    indicators: list[str],
    country: str | None,
    year_min: int | None,
    year_max: int | None,
) -> dict[str, Any]:
    url = build_source_url(version=version)
    archive_cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_cache_dir / f"V-Dem-CY-Core-v{version}.zip"

    if not archive_path.exists():
        timeout = float(runtime_http.get("timeout_seconds", 120))
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        with archive_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)

    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    with zipfile.ZipFile(archive_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV file found inside {archive_path.name}")
        with zf.open(csv_names[0]) as csv_fh:
            text = io.TextIOWrapper(csv_fh, encoding="utf-8", newline="")
            reader = csv.DictReader(text)
            wanted_indicators = set(indicators)
            columns = [c for c in (reader.fieldnames or []) if c in CORE_META_COLUMNS or c in wanted_indicators]
            for record in reader:
                try:
                    country_code = str(record.get("country_text_id", "")).strip().upper()
                    year_str = str(record.get("year", "")).strip()
                    year_val = int(year_str) if year_str else None
                except (TypeError, ValueError):
                    continue
                if country and country_code != country:
                    continue
                if year_min is not None and (year_val is None or year_val < year_min):
                    continue
                if year_max is not None and (year_val is None or year_val > year_max):
                    continue
                slim = {col: record.get(col) for col in columns}
                rows.append(slim)

    return {
        "source_url": url,
        "archive_path": str(archive_path),
        "version": version,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }
