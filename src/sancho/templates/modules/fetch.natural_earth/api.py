from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

# Natural Earth GeoJSON URLs (via GitHub mirror -- stable, versioned)
_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
_ADM0_URL = f"{_BASE}/ne_110m_admin_0_countries.geojson"
_ADM1_URL = f"{_BASE}/ne_110m_admin_1_states_provinces.geojson"

_UA = "SanchoFetch/1.0 (sancho)"


def fetch_boundaries(
    *,
    runtime_http: dict[str, Any],
    level: str,
    country: str | None,
    name: str | None,
) -> dict[str, Any]:
    url = _ADM1_URL if level == "adm1" else _ADM0_URL
    timeout = float(runtime_http.get("timeout_seconds", 60))

    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
    resp.raise_for_status()
    geojson = resp.json()

    features = geojson.get("features", [])

    # Filter by country ISO code
    if country:
        country_upper = country.upper()
        features = [
            f for f in features
            if _prop(f, "ISO_A3") == country_upper
            or _prop(f, "ISO_A2") == country_upper
            or _prop(f, "ADM0_A3") == country_upper
            or _prop(f, "iso_a3") == country_upper
        ]

    # Filter by name substring
    if name:
        name_lower = name.lower()
        features = [
            f for f in features
            if name_lower in _prop(f, "NAME").lower()
            or name_lower in _prop(f, "name").lower()
            or name_lower in _prop(f, "ADMIN").lower()
        ]

    rows = []
    for f in features:
        props = f.get("properties", {})
        rows.append({
            "name": props.get("NAME") or props.get("name", ""),
            "iso_a3": props.get("ISO_A3") or props.get("ADM0_A3", ""),
            "iso_a2": props.get("ISO_A2", ""),
            "admin_level": level,
            "geometry_type": f.get("geometry", {}).get("type", ""),
            "properties": props,
        })

    return {
        "source_url": url,
        "level": level,
        "feature_count": len(rows),
        "rows": rows,
        "raw": geojson,
    }


def _prop(feature: dict, key: str) -> str:
    return str(feature.get("properties", {}).get(key, ""))
