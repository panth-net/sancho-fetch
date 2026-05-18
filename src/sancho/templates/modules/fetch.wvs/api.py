from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

DOWNLOAD_URL = "https://www.worldvaluessurvey.org/WVSDocumentationWV7.jsp"

_COUNTRY_COL_CANDIDATES = (
    "B_COUNTRY_ALPHA",
    "COUNTRY_ALPHA",
    "C_COW_ALPHA",
    "S003ALPHA",
)
_WAVE_COL_CANDIDATES = ("A_WAVE", "S002VS", "S002")


def build_source_url() -> str:
    return DOWNLOAD_URL


def _resolve_data_file(local_path: Path) -> tuple[Path, str]:
    """Return (path_to_data_file, file_kind) where kind is 'csv' or 'sav'.

    Handles three layouts: bare .csv, bare .sav, and .zip containing one of
    them. ZIP contents are extracted to the same directory the zip lives in.
    """
    suffix = local_path.suffix.lower()
    if suffix == ".csv":
        return local_path, "csv"
    if suffix == ".sav":
        return local_path, "sav"
    if suffix == ".zip":
        with zipfile.ZipFile(local_path) as zf:
            members = zf.namelist()
            csvs = [n for n in members if n.lower().endswith(".csv")]
            savs = [n for n in members if n.lower().endswith(".sav")]
            if not csvs and not savs:
                raise RuntimeError(
                    f"No .csv or .sav file found inside ZIP: {local_path}"
                )
            chosen = (csvs or savs)[0]
            zf.extract(chosen, local_path.parent)
            extracted = local_path.parent / chosen
            return extracted, "csv" if chosen.lower().endswith(".csv") else "sav"
    raise RuntimeError(
        f"Unsupported WVS file extension: {local_path.suffix} "
        "(expected .csv, .sav, or .zip containing one)"
    )


def _matches_country(record: dict[str, Any], header: list[str], country: str | None) -> bool:
    if not country:
        return True
    target = country.upper()
    for col in header:
        if col.upper() in _COUNTRY_COL_CANDIDATES:
            if str(record.get(col, "")).upper() == target:
                return True
    return False


def _matches_wave(record: dict[str, Any], header: list[str], wave: int | None) -> bool:
    if wave is None:
        return True
    target = str(wave)
    for col in header:
        if col.upper() in _WAVE_COL_CANDIDATES:
            v = record.get(col)
            if v is None or v == "":
                continue
            try:
                if str(int(float(v))) == target:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _read_csv_rows(
    path: Path, *, country: str | None, wave: int | None, max_rows: int = 10000,
) -> tuple[list[dict[str, Any]], list[str], int]:
    """Stream rows from CSV applying country/wave filters inline.

    Returns (filtered_rows[:max_rows], header, total_rows_in_file).
    """
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        total = 0
        for record in reader:
            total += 1
            if not _matches_country(record, header, country):
                continue
            if not _matches_wave(record, header, wave):
                continue
            if len(rows) < max_rows:
                rows.append(record)
        return rows, header, total


def _read_sav_rows(
    path: Path, *, country: str | None, wave: int | None, max_rows: int = 10000,
) -> tuple[list[dict[str, Any]], list[str], int]:
    try:
        import pyreadstat
    except ImportError:
        raise RuntimeError(
            "WVS .sav files require pyreadstat. Install with: pip install pyreadstat "
            "or download the CSV variant from worldvaluessurvey.org instead."
        )
    df, _meta = pyreadstat.read_sav(str(path))
    header = list(df.columns)
    total = len(df)
    records = df.to_dict(orient="records")
    out: list[dict[str, Any]] = []
    for r in records:
        if not _matches_country(r, header, country):
            continue
        if not _matches_wave(r, header, wave):
            continue
        if len(out) < max_rows:
            out.append(r)
    return out, header, total


def fetch_wvs(
    *,
    runtime_http: dict[str, Any],
    file_path: str | None,
    country: str | None,
    wave: int | None,
) -> dict[str, Any]:
    if not file_path:
        return {
            "source_url": DOWNLOAD_URL,
            "status": "manual_download_required",
            "instructions": (
                "World Values Survey requires a license agreement for data access.\n"
                "1. Visit https://www.worldvaluessurvey.org/WVSDocumentationWV7.jsp\n"
                "2. Accept the license terms\n"
                "3. Download a CSV (.csv or .csv.zip) or SPSS (.sav) file\n"
                "4. Pass the local path via file_path.\n"
                'Example: {"file_path": "fetched-data/WVS_Cross-National_Wave_7_csv_v6_0.zip"}'
            ),
            "rows": [],
            "row_count": 0,
        }

    local_path = Path(file_path)
    if not local_path.exists():
        raise FileNotFoundError(f"WVS file not found: {file_path}")

    data_path, kind = _resolve_data_file(local_path)
    if kind == "csv":
        rows, header, total = _read_csv_rows(data_path, country=country, wave=wave)
    else:
        rows, header, total = _read_sav_rows(data_path, country=country, wave=wave)

    return {
        "source_url": DOWNLOAD_URL,
        "file_path": str(data_path),
        "file_kind": kind,
        "variables": header[:50],
        "total_rows": total,
        "rows": rows,
        "row_count": len(rows),
    }
