"""Shared catalog-discovery helper for SDMX-REST dataflow catalogs.

SDMX is the standard for statistical data exchange used by OECD, IMF, ECB,
Eurostat, UN, and many national statistics offices. Every SDMX provider
exposes a `/dataflow/all/all` (or `/dataflow/{agency}/all/latest`) endpoint
that enumerates every dataflow (dataset) it hosts -- along with name,
agency, version, and a reference to the DSD (data-structure definition).

Each module's discovery.py imports `discover_sdmx` and passes its own
(provider_id, base_url, dataflow_path) triple.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


_USER_AGENT = "sancho-sdmx-discovery/1.0"
_ACCEPT_HEADER = (
    "application/vnd.sdmx.structure+json;version=1.0.0,"
    "application/vnd.sdmx.structure+xml;version=2.1;q=0.9,"
    "application/json;q=0.8,application/xml;q=0.7"
)

# SDMX 2.1 structure namespaces
_SDMX_NS = {
    "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "str": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}


def _parse_sdmx_xml_dataflows(content: bytes) -> list[dict[str, Any]]:
    """Parse SDMX-ML XML dataflow response -> list of flat dicts."""
    root = ET.fromstring(content)
    out: list[dict[str, Any]] = []
    for df in root.iter(f"{{{_SDMX_NS['str']}}}Dataflow"):
        entry: dict[str, Any] = {
            "id": df.attrib.get("id"),
            "agencyID": df.attrib.get("agencyID"),
            "version": df.attrib.get("version"),
            "isFinal": df.attrib.get("isFinal"),
        }
        # English name is typically the first Name child.
        for name_el in df.findall(f"{{{_SDMX_NS['com']}}}Name"):
            lang = name_el.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
            if lang == "en":
                entry["name"] = name_el.text
                break
        if "name" not in entry:
            first = df.find(f"{{{_SDMX_NS['com']}}}Name")
            if first is not None:
                entry["name"] = first.text
        # Description
        for desc_el in df.findall(f"{{{_SDMX_NS['com']}}}Description"):
            lang = desc_el.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
            if lang == "en":
                entry["description"] = desc_el.text
                break
        # Structure reference
        struct_el = df.find(f"{{{_SDMX_NS['str']}}}Structure")
        if struct_el is not None:
            ref = struct_el.find(f"{{{_SDMX_NS['com']}}}Ref") or struct_el.find("Ref")
            if ref is not None:
                entry["structure"] = {
                    "id": ref.attrib.get("id"),
                    "agencyID": ref.attrib.get("agencyID"),
                    "version": ref.attrib.get("version"),
                    "class": ref.attrib.get("class"),
                    "package": ref.attrib.get("package"),
                }
        out.append(entry)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_dataflows(url: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch an SDMX dataflow endpoint and parse as JSON or SDMX-ML XML."""
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=180,
            headers={"User-Agent": _USER_AGENT, "Accept": _ACCEPT_HEADER},
        )
        last_status = resp.status_code
        resp.raise_for_status()
    except Exception as exc:
        return [], {
            "id": "dataflow",
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    content = resp.content
    dataflows: list[dict[str, Any]] = []
    # Try JSON first.
    if content[:1] in (b"{", b"["):
        try:
            data = json.loads(content.decode("utf-8"))
            if isinstance(data, dict):
                df_list = (data.get("data") or {}).get("dataflows", [])
                if isinstance(df_list, list):
                    dataflows = [d for d in df_list if isinstance(d, dict)]
        except Exception:
            pass
    # Fall back to XML (SDMX-ML) -- OECD returns XML despite Accept headers.
    if not dataflows and content[:1] == b"<":
        try:
            dataflows = _parse_sdmx_xml_dataflows(content)
        except Exception as exc:
            return [], {
                "id": "dataflow",
                "url": url,
                "status": "error",
                "http_status": last_status,
                "count": 0,
                "error": f"xml parse: {exc}",
                "fetched_at": _now_iso(),
            }
    return dataflows, {
        "id": "dataflow",
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": len(dataflows),
        "error": "",
        "fetched_at": _now_iso(),
    }


def _simplify_dataflow(df: dict[str, Any]) -> dict[str, Any]:
    # Name: JSON-style (names dict) or XML-flattened (name string)
    name = df.get("name")
    if not name:
        names = df.get("names") or {}
        if isinstance(names, dict):
            name = names.get("en") or (next(iter(names.values()), "") if names else "")
    description = df.get("description")
    if not description:
        descriptions = df.get("descriptions") or {}
        if isinstance(descriptions, dict):
            description = descriptions.get("en") or (next(iter(descriptions.values()), "") if descriptions else "")
    return {
        "id": df.get("id"),
        "agencyID": df.get("agencyID") or df.get("agencyId"),
        "version": df.get("version"),
        "name": name,
        "description": description,
        "structure": df.get("structure"),
        "annotations_count": len(df.get("annotations") or []),
    }


def discover_sdmx(
    *,
    module_dir: Path,
    provider_id: str,
    base_url: str,
    dataflow_path: str = "/dataflow/all/all",
    docs_url: str = "",
    offline: bool = False,
    schema_version: str = "1.0",
    family_families: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch the dataflow catalog from *base_url + dataflow_path* and write catalog files."""
    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    url = f"{base_url.rstrip('/')}{dataflow_path}"
    dataflows, snap = _fetch_dataflows(url)
    snapshots = [snap]
    if snap.get("status") != "ok":
        raise RuntimeError(f"{provider_id} SDMX dataflow fetch failed: {snap.get('error')}")

    simplified = [_simplify_dataflow(df) for df in dataflows]
    agencies: dict[str, int] = {}
    for df in simplified:
        a = df.get("agencyID") or "(unknown)"
        agencies[a] = agencies.get(a, 0) + 1

    effective_families = family_families or [
        {
            "id": "sdmx.dataflow",
            "base_aliases": ["v1"],
            "base_url": base_url,
            "path_templates": [
                "/dataflow/all/all",
                "/dataflow/{agency}/{id}/{version}",
                "/data/{agency},{dataflow},{version}/{key}",
                "/datastructure/{agency}/{id}/{version}",
                "/codelist/{agency}/{id}/{version}",
            ],
            "methods": ["GET"],
            "query_params": {
                "startPeriod": {"type": "string", "description": "Start period"},
                "endPeriod": {"type": "string", "description": "End period"},
                "dimensionAtObservation": {"type": "string", "examples": ["TIME_PERIOD", "AllDimensions"]},
                "detail": {"type": "string", "examples": ["full", "dataonly", "serieskeysonly", "nodata"]},
                "format": {"type": "string", "examples": ["jsondata", "structurespecific", "generic"]},
            },
            "response_mode": "json",
            "envelope_key": "data.dataflows",
            "description": f"SDMX-REST dataflow catalog for {provider_id}. See catalog.json.dataflows[].",
            "source_refs": [docs_url] if docs_url else [],
        },
    ]

    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": effective_families,
        "dataflows": simplified,
        "agencies": agencies,
    }
    stats = {
        "family_count": len(effective_families),
        "dataflow_count": len(simplified),
        "dataflows_count": len(simplified),
        "agency_count": len(agencies),
        "agencies_count": len(agencies),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [docs_url] if docs_url else [],
        },
    }

    (module_dir / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )
    (module_dir / "catalog.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )

    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "family_count": stats["family_count"],
        "dataflow_count": stats["dataflow_count"],
        "agency_count": stats["agency_count"],
    }
