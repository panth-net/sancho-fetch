from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

import requests

URL_TEMPLATE = (
    "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NHIS/{year}/{kind}{yy}csv.zip"
)


def build_source_url(*, year: int, file_kind: str) -> str:
    yy = str(year)[-2:]
    # Special files use full year, not 2-digit
    if file_kind == "final_pair_weight":
        return (
            f"https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NHIS/"
            f"{year}/final_pair_weight{year}csv.zip"
        )
    return URL_TEMPLATE.format(year=year, kind=file_kind, yy=yy)


def fetch_nhis(
    *,
    runtime_http: dict[str, Any],
    year: int,
    file_kind: str,
    limit: int,
) -> dict[str, Any]:
    url = build_source_url(year=year, file_kind=file_kind)
    timeout = float(runtime_http.get("timeout_seconds", 120))
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": runtime_http.get(
                "user_agent",
                "sancho-fetch/1.0",
            )
        },
    )
    r.raise_for_status()
    content = r.content
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    total_rows = 0
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(
                f"No .csv file inside NHIS ZIP at {url}"
            )
        csv_name = csv_names[0]
        with zf.open(csv_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text)
            columns = list(reader.fieldnames or [])
            for record in reader:
                total_rows += 1
                if len(rows) < limit:
                    rows.append(record)
    return {
        "source_url": url,
        "file_kind": file_kind,
        "year": year,
        "csv_name": csv_name,
        "columns": columns[:50],
        "total_columns": len(columns),
        "total_rows_in_file": total_rows,
        "rows": rows,
        "row_count": len(rows),
    }
