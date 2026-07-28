from __future__ import annotations

import csv
import io
import re
from html import unescape
from typing import Any

import requests

# Primary: World Bank Data360 CSV (fast, reliable)
CSV_URL = "https://data360files.worldbank.org/data360-data/data/UN_EGDI/UN_EGDI_WIDEF.csv"

# Fallback: UN ASP.NET Data Center (slow, flaky)
SOURCE_URL = "https://publicadministration.un.org/egovkb/en-us/Data-Center"

_YEAR_COLUMNS = [str(y) for y in range(2003, 2030)]
_UA = "SanchoFetch/1.0 (sancho)"


def build_source_url(*, year: int | None) -> str:
    return CSV_URL


def _fetch_data360_csv(
    *,
    timeout: float,
    year: int | None,
    country: str | None,
    indicator: str | None,
) -> dict[str, Any]:
    """Download and parse the Data360 wide CSV into long-format rows."""
    resp = requests.get(CSV_URL, headers={"User-Agent": _UA}, timeout=timeout)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    rows: list[dict[str, Any]] = []
    for record in reader:
        ref_area = record.get("REF_AREA", "").strip()
        ind = record.get("INDICATOR", "").strip()

        if country and ref_area.upper() != country.upper():
            continue
        if indicator and indicator.upper() not in ind.upper():
            continue

        for col in record:
            if col not in _YEAR_COLUMNS:
                continue
            val = record[col].strip() if record[col] else ""
            if not val:
                continue
            if year is not None and int(col) != year:
                continue
            try:
                score = float(val)
            except ValueError:
                continue
            rows.append({
                "country_iso2": ref_area,
                "indicator": ind,
                "year": int(col),
                "value": score,
            })

    return {"source_url": CSV_URL, "rows": rows, "row_count": len(rows)}


def fetch_egdi(
    *,
    runtime_http: dict[str, Any],
    year: int | None,
    country: str | None,
) -> dict[str, Any]:
    """Fetch EGDI data. Primary: Data360 CSV. Fallback: UN scraper."""
    timeout = float(runtime_http.get("timeout_seconds", 60))

    try:
        return _fetch_data360_csv(
            timeout=timeout, year=year, country=country, indicator="UN_EGDI_EGDI",
        )
    except Exception:
        pass

    return _fetch_un_scraper(timeout=min(timeout, 120), year=year, country=country)


def _extract_form_fields(html: str) -> dict[str, str]:
    fields = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        match = re.search(rf'id="{name}"[^>]*value="([^"]*)"', html, re.DOTALL)
        if match:
            fields[name] = match.group(1)
    return fields


def _extract_select_name(html: str, suffix: str) -> str | None:
    match = re.search(rf'name="([^"]*{suffix})"', html)
    return match.group(1) if match else None


def _parse_data_array(html: str) -> list[dict[str, Any]]:
    match = re.search(r'\[\s*\[\s*"[A-Z]{2}"', html)
    if not match:
        return []
    start = html.rfind('[', 0, match.start() + 1)
    depth, end = 0, start
    for i in range(start, min(start + 500_000, len(html))):
        if html[i] == '[':
            depth += 1
        elif html[i] == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    entries = re.findall(
        r'\["([A-Z]{2})",\s*([\d.]+),\s*"((?:[^"\\]|\\.)*)"\]',
        html[start:end],
    )
    results: list[dict[str, Any]] = []
    for iso2, score_str, tooltip_raw in entries:
        tooltip = unescape(tooltip_raw.replace('\\"', '"'))
        nm = re.search(r'<b>([^<]+)</b>', tooltip)
        rk = re.search(r'Rank[:\s]*(\d+)', tooltip, re.IGNORECASE)
        try:
            score = float(score_str)
        except ValueError:
            score = None
        results.append({
            "country_iso2": iso2,
            "country_name": nm.group(1).strip() if nm else "",
            "egdi_score": score,
            "rank": int(rk.group(1)) if rk else None,
        })
    return results


def _fetch_un_scraper(
    *, timeout: float, year: int | None, country: str | None,
) -> dict[str, Any]:
    session = requests.Session()
    page = session.get(SOURCE_URL, timeout=timeout)
    page.raise_for_status()
    form_fields = _extract_form_fields(page.text)
    year_name = _extract_select_name(page.text, "ddlYear")
    index_name = _extract_select_name(page.text, "ddlIndexTypes")
    submit_name = _extract_select_name(page.text, "btnSubmit")
    effective_year = year or 2024
    post_data = {**form_fields}
    if year_name:
        post_data[year_name] = str(effective_year)
    if index_name:
        post_data[index_name] = "2"
    if submit_name:
        post_data[submit_name] = "Submit"
    result = session.post(SOURCE_URL, data=post_data, timeout=timeout)
    result.raise_for_status()
    entries = _parse_data_array(result.text)
    rows = []
    for entry in entries:
        if country and entry.get("country_iso2", "").upper() != country[:2].upper():
            continue
        entry["year"] = effective_year
        rows.append(entry)
    return {"source_url": SOURCE_URL, "year": effective_year, "rows": rows, "row_count": len(rows)}
