from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import requests

from sancho.runtime.http import HttpClient

# ---------------------------------------------------------------------------
# SDMX endpoints for IMF CDIS
# ---------------------------------------------------------------------------

DATAFLOW_URL = (
    "https://sdmxcentral.imf.org/ws/public/sdmxapi/rest/dataflow/IMF/1DI/1.0"
)
DATA_URL_TEMPLATE = (
    "https://sdmxcentral.imf.org/ws/public/sdmxapi/rest/data/"
    "IMF,1DI,1.0/{country_filter}?startPeriod={start}&endPeriod={end}"
)
FALLBACK_DATAFLOW_URL = (
    "https://dataservices.imf.org/REST/SDMX_JSON.svc/Dataflow"
)

SDMX_NS = {
    "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "str": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
    "gen": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_source_url(
    *, period: str | None, country: str | None,
) -> str:
    """Return the canonical source URL for provenance tracking."""
    if period and country:
        return DATA_URL_TEMPLATE.format(
            country_filter=country, start=period, end=period,
        )
    return DATAFLOW_URL


# ---------------------------------------------------------------------------
# SDMX XML parsing helpers
# ---------------------------------------------------------------------------


def _parse_dataflow_xml(xml_text: str) -> dict[str, Any]:
    """Extract dataflow metadata from SDMX structure response."""
    root = ET.fromstring(xml_text)
    dataflows: list[dict[str, Any]] = []

    for df in root.iter(f"{{{SDMX_NS['str']}}}Dataflow"):
        entry: dict[str, Any] = {
            "id": df.attrib.get("id", ""),
            "agency": df.attrib.get("agencyID", ""),
            "version": df.attrib.get("version", ""),
        }
        name_el = df.find(f"{{{SDMX_NS['com']}}}Name")
        if name_el is not None and name_el.text:
            entry["name"] = name_el.text.strip()
        dataflows.append(entry)

    return {"dataflows": dataflows, "count": len(dataflows)}


def _parse_data_xml(xml_text: str) -> list[dict[str, Any]]:
    """Parse SDMX generic-data XML into flat observation rows."""
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []

    for series in root.iter(f"{{{SDMX_NS['gen']}}}Series"):
        series_keys: dict[str, str] = {}
        for key_val in series.iter(f"{{{SDMX_NS['gen']}}}Value"):
            kid = key_val.attrib.get("id", "")
            kval = key_val.attrib.get("value", "")
            if kid:
                series_keys[kid] = kval

        country_iso = series_keys.get("REF_AREA", "")
        partner_iso = series_keys.get("COUNTERPART_AREA", "")
        direction = series_keys.get("INDICATOR", "")

        for obs in series.iter(f"{{{SDMX_NS['gen']}}}Obs"):
            dim_el = obs.find(f"{{{SDMX_NS['gen']}}}ObsDimension")
            val_el = obs.find(f"{{{SDMX_NS['gen']}}}ObsValue")
            period = dim_el.attrib.get("value", "") if dim_el is not None else ""
            value_str = val_el.attrib.get("value", "") if val_el is not None else ""
            try:
                value = float(value_str)
            except (ValueError, TypeError):
                value = None
            rows.append({
                "country_iso": country_iso,
                "partner_iso": partner_iso,
                "direction": direction,
                "period": period,
                "value": value,
            })

    return rows


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


def _fetch_dataflow_structure(timeout: float) -> dict[str, Any]:
    """Fetch the CDIS dataflow structure from the primary SDMX endpoint."""
    resp = requests.get(
        DATAFLOW_URL,
        headers={"Accept": "application/xml"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return _parse_dataflow_xml(resp.text)


def _fetch_dataflow_fallback(client: HttpClient) -> dict[str, Any]:
    """Fetch dataflow list from the JSON fallback endpoint."""
    payload = client.request_json("GET", FALLBACK_DATAFLOW_URL)
    dataflows: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        structure = payload.get("Structure", {})
        dfs = structure.get("Dataflows", {}).get("Dataflow", [])
        if isinstance(dfs, list):
            for df in dfs:
                if not isinstance(df, dict):
                    continue
                name_obj = df.get("Name", {})
                name = name_obj.get("#text", "") if isinstance(name_obj, dict) else ""
                dataflows.append({
                    "id": df.get("KeyFamilyRef", {}).get("KeyFamilyID", ""),
                    "name": name,
                })

    return {"dataflows": dataflows, "count": len(dataflows)}


def _fetch_data(
    *, period: str, country: str | None, timeout: float,
) -> list[dict[str, Any]]:
    """Fetch CDIS observation data for the given period and country."""
    country_filter = country if country else "."
    url = DATA_URL_TEMPLATE.format(
        country_filter=country_filter, start=period, end=period,
    )
    resp = requests.get(
        url,
        headers={"Accept": "application/xml"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return _parse_data_xml(resp.text)


# ---------------------------------------------------------------------------
# Public fetch entry point
# ---------------------------------------------------------------------------


def fetch_cdis(
    runtime_http: dict[str, Any],
    period: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    """Fetch IMF CDIS data; fall back to metadata manifest on failure."""
    timeout = runtime_http.get("timeout_seconds", 30)
    client = HttpClient(**runtime_http)
    source_url = build_source_url(period=period, country=country)

    # Try to get the dataflow structure first
    try:
        structure = _fetch_dataflow_structure(timeout=timeout)
    except Exception:
        try:
            structure = _fetch_dataflow_fallback(client)
        except Exception:
            structure = {"dataflows": [], "count": 0}

    # If a period is specified, fetch actual data observations
    if period:
        try:
            rows = _fetch_data(
                period=period, country=country, timeout=timeout,
            )
            return {
                "source_url": source_url,
                "rows": rows,
                "row_count": len(rows),
                "structure": structure,
            }
        except Exception:
            # Fall back to dataflow metadata as rows
            dataflows = structure.get("dataflows", [])
            return {
                "source_url": source_url,
                "rows": dataflows,
                "row_count": len(dataflows),
                "structure": structure,
                "note": "Data query failed; returning dataflow metadata as rows.",
            }

    # No period: return structure manifest (dataflows as rows)
    dataflows = structure.get("dataflows", [])
    return {
        "source_url": source_url,
        "rows": dataflows,
        "row_count": len(dataflows),
        "structure": structure,
    }
