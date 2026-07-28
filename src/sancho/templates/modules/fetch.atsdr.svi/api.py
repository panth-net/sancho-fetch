from __future__ import annotations

import csv
import io
from typing import Any

import requests


def build_source_url(*, year: int) -> str:
    return f"https://svi.cdc.gov/Documents/Data/{year}/csv/States/SVI_{year}_US.csv"


def fetch_svi(
    *,
    runtime_http: dict[str, Any],
    year: int,
    state: str | None,
    limit: int,
) -> dict[str, Any]:
    url = build_source_url(year=year)
    timeout = float(runtime_http.get("timeout_seconds", 180))
    state_filter = state.upper() if state else None

    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    total_rows = 0
    # Prefer the 2-letter abbreviation column when present (cleaner match).
    state_col_candidates = ("ST_ABBR", "STATE_ABBR", "STATE")

    # The file is ~60MB; download fully then parse. Avoid streaming because
    # requests' raw socket gets closed before the iterator finishes.
    r = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (sancho-fetch)"},
    )
    r.raise_for_status()
    text_stream = io.StringIO(r.content.decode("utf-8", errors="replace"))
    reader = csv.DictReader(text_stream)
    columns = list(reader.fieldnames or [])
    # Iterate through CANDIDATES (priority order) and pick the first that
    # exists in the column list. Iterating through columns instead would
    # always pick STATE over ST_ABBR because STATE comes first in the file.
    upper_to_actual = {c.upper(): c for c in columns}
    state_col = next(
        (upper_to_actual[c] for c in state_col_candidates if c in upper_to_actual),
        None,
    )
    for record in reader:
        total_rows += 1
        if state_filter and state_col:
            if str(record.get(state_col, "")).upper() != state_filter:
                # SVI uses full state names (e.g. "California"), so also try
                # a name-prefix match.
                state_val = str(record.get(state_col, "")).upper()
                if not state_val.startswith(state_filter):
                    continue
        if len(rows) < limit:
            rows.append(record)

    return {
        "source_url": url,
        "year": year,
        "state_filter": state_filter,
        "columns": columns[:50],
        "total_columns": len(columns),
        "total_rows_in_file": total_rows,
        "rows": rows,
        "row_count": len(rows),
    }
