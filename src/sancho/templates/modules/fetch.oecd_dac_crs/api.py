from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import requests

# ---------------------------------------------------------------------------
# OECD DAC/CRS SDMX dataflow endpoints
# ---------------------------------------------------------------------------

DATAFLOW_URLS: dict[str, str] = {
    "CRS": (
        "https://sdmx.oecd.org/dcd-public/rest/dataflow/"
        "OECD.DCD.FSD/DSD_CRS@DF_CRS/1.5"
    ),
    "CPA": (
        "https://sdmx.oecd.org/dcd-public/rest/dataflow/"
        "OECD.DCD.FSD/DSD_CPA@DF_CRS_CPA/1.3"
    ),
}

# SDMX v2.1 structure namespace
NS_STR = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
NS_COM = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
NS = {
    "str": NS_STR,
    "com": NS_COM,
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_source_url(*, dataflow: str = "CRS") -> str:
    """Return the SDMX endpoint URL for the given dataflow."""
    key = dataflow.upper()
    if key not in DATAFLOW_URLS:
        raise ValueError(
            f"Unknown dataflow '{dataflow}'. "
            f"Supported: {', '.join(sorted(DATAFLOW_URLS))}"
        )
    return DATAFLOW_URLS[key]


# ---------------------------------------------------------------------------
# SDMX XML parsing
# ---------------------------------------------------------------------------


def _parse_annotations(dataflow_el: ET.Element) -> list[dict[str, str]]:
    """Extract EXT_RESOURCE annotations from a Dataflow element.

    SDMX annotations with type EXT_RESOURCE contain pipe-delimited
    label|url pairs in their AnnotationText elements.
    """
    resources: list[dict[str, str]] = []
    for annotation in dataflow_el.iter(f"{{{NS_STR}}}Annotation"):
        ann_type_el = annotation.find(f"{{{NS_COM}}}AnnotationType")
        if ann_type_el is None:
            ann_type_el = annotation.find(f"{{{NS_STR}}}AnnotationType")
        if ann_type_el is None or ann_type_el.text != "EXT_RESOURCE":
            continue

        for ann_text in annotation.iter(f"{{{NS_COM}}}AnnotationText"):
            text = (ann_text.text or "").strip()
            if not text:
                continue
            # Format: "label|url" or just a bare URL
            if "|" in text:
                parts = text.split("|", 1)
                resources.append({"label": parts[0].strip(), "url": parts[1].strip()})
            else:
                resources.append({"label": "", "url": text})

    return resources


def _parse_dataflow_metadata(
    root: ET.Element,
) -> dict[str, Any]:
    """Parse a Dataflow element for name, description, and dimensions."""
    dataflow_el = root.find(f".//{{{NS_STR}}}Dataflow")
    if dataflow_el is None:
        return {"name": None, "description": None, "dimensions": []}

    # Name
    name_el = dataflow_el.find(f"{{{NS_COM}}}Name")
    name = name_el.text.strip() if name_el is not None and name_el.text else None

    # Description
    desc_el = dataflow_el.find(f"{{{NS_COM}}}Description")
    description = desc_el.text.strip() if desc_el is not None and desc_el.text else None

    # Dimensions from the Structure reference
    dimensions: list[str] = []
    for dim in dataflow_el.iter(f"{{{NS_STR}}}Dimension"):
        dim_id = dim.get("id")
        if dim_id:
            dimensions.append(dim_id)

    return {"name": name, "description": description, "dimensions": dimensions}


def _parse_sdmx_response(xml_bytes: bytes) -> dict[str, Any]:
    """Parse the full SDMX XML response into structured data."""
    root = ET.fromstring(xml_bytes)
    metadata = _parse_dataflow_metadata(root)

    # Find the Dataflow element for annotations
    dataflow_el = root.find(f".//{{{NS_STR}}}Dataflow")
    resources: list[dict[str, str]] = []
    if dataflow_el is not None:
        resources = _parse_annotations(dataflow_el)

    # Build rows: one per resource URL found
    rows: list[dict[str, Any]] = []
    for res in resources:
        rows.append({
            "dataflow_name": metadata.get("name"),
            "resource_label": res["label"],
            "resource_url": res["url"],
        })

    return {
        "metadata": metadata,
        "resources": resources,
        "rows": rows,
        "row_count": len(rows),
    }


# ---------------------------------------------------------------------------
# Public fetch entry point
# ---------------------------------------------------------------------------


def fetch_dac_crs(
    runtime_http: dict[str, Any],
    dataflow: str = "CRS",
) -> dict[str, Any]:
    """Fetch OECD DAC/CRS SDMX dataflow metadata and resource URLs."""
    timeout = runtime_http.get("timeout_seconds", 30)
    source_url = build_source_url(dataflow=dataflow)

    headers = {
        "Accept": "application/xml",
        "User-Agent": "SanchoFetch/1.0 (sancho)",
    }
    resp = requests.get(source_url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    parsed = _parse_sdmx_response(resp.content)

    return {
        "source_url": source_url,
        "dataflow": dataflow.upper(),
        "metadata": parsed.get("metadata", {}),
        "resources": parsed["resources"],
        "rows": parsed["rows"],
        "row_count": parsed["row_count"],
    }
