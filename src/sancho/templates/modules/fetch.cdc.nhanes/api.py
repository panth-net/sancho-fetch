from __future__ import annotations

import io
import tempfile
from typing import Any

import requests

# Map cycle letter to start year (the "cycle directory" on the NCHS server).
CYCLE_START_YEAR = {
    "A": "1999",
    "B": "2001",
    "C": "2003",
    "D": "2005",
    "E": "2007",
    "F": "2009",
    "G": "2011",
    "H": "2013",
    "I": "2015",
    "J": "2017",
    "K": "2019",
    "L": "2021",
    "M": "2023",
}


def build_source_url(*, cycle: str, component: str) -> str:
    cycle_upper = cycle.upper()
    start_year = CYCLE_START_YEAR.get(
        cycle_upper, "2017"
    )
    return (
        "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/"
        f"{start_year}/DataFiles/{component.upper()}_{cycle_upper}.XPT"
    )


def fetch_nhanes(
    *,
    runtime_http: dict[str, Any],
    cycle: str,
    component: str,
    limit: int,
) -> dict[str, Any]:
    try:
        import pyreadstat
    except ImportError:
        raise RuntimeError(
            "fetch.cdc.nhanes requires pyreadstat. "
            "Install with: pip install pyreadstat"
        )
    url = build_source_url(cycle=cycle, component=component)
    timeout = float(runtime_http.get("timeout_seconds", 120))
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": runtime_http.get(
                "user_agent",
                "Mozilla/5.0 (sancho-fetch)",
            )
        },
    )
    r.raise_for_status()
    if not r.content.startswith(b"HEADER REC"):
        raise RuntimeError(
            f"NHANES URL did not return a SAS Transport file: {url}"
        )
    # pyreadstat needs a real file -- write to a temp path.
    with tempfile.NamedTemporaryFile(
        suffix=".XPT", delete=False,
    ) as tmp:
        tmp.write(r.content)
        tmp_path = tmp.name
    try:
        # Newer NHANES cycles (e.g. L = 2021-2023) include cp1252 bytes that
        # crash the default UTF-8 decoder. Try UTF-8 first, fall back to cp1252.
        try:
            df, _meta = pyreadstat.read_xport(tmp_path)
        except UnicodeDecodeError:
            df, _meta = pyreadstat.read_xport(tmp_path, encoding="cp1252")
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    columns = list(df.columns)
    total_rows = len(df)
    rows = df.head(limit).to_dict(orient="records")
    return {
        "source_url": url,
        "cycle": cycle.upper(),
        "component": component.upper(),
        "columns": columns,
        "total_columns": len(columns),
        "total_rows_in_file": total_rows,
        "rows": rows,
        "row_count": len(rows),
    }
