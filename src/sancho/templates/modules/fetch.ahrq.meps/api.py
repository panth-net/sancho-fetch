from __future__ import annotations

import io
import os
import tempfile
import zipfile
from typing import Any

import requests


def build_source_url(*, puf_id: str) -> str:
    pid = puf_id.lower()
    return (
        f"https://meps.ahrq.gov/mepsweb/data_files/pufs/{pid}/{pid}dta.zip"
    )


def fetch_meps(
    *,
    runtime_http: dict[str, Any],
    puf_id: str,
    limit: int,
) -> dict[str, Any]:
    try:
        import pyreadstat
    except ImportError:
        raise RuntimeError(
            "fetch.ahrq.meps requires pyreadstat. Install with: pip install pyreadstat"
        )
    url = build_source_url(puf_id=puf_id)
    timeout = float(runtime_http.get("timeout_seconds", 180))
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
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        dta_names = [n for n in zf.namelist() if n.lower().endswith(".dta")]
        if not dta_names:
            raise RuntimeError(
                f"No .dta file inside MEPS ZIP at {url}"
            )
        dta_name = dta_names[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extract(dta_name, tmpdir)
            tmp_path = os.path.join(tmpdir, dta_name)
            df, _meta = pyreadstat.read_dta(tmp_path)
    columns = list(df.columns)
    total_rows = len(df)
    rows = df.head(limit).to_dict(orient="records")
    return {
        "source_url": url,
        "puf_id": puf_id.lower(),
        "dta_name": dta_name,
        "columns": columns[:50],
        "total_columns": len(columns),
        "total_rows_in_file": total_rows,
        "rows": rows,
        "row_count": len(rows),
    }
