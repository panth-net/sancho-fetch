from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # GeoJSON FeatureCollection (alerts, stations, zones)
        feats = raw.get("features")
        if isinstance(feats, list):
            return feats
        # JSON-LD @graph (product types)
        graph = raw.get("@graph")
        if isinstance(graph, list):
            return graph
        # Forecast object: properties.periods is the row-list
        props = raw.get("properties")
        if isinstance(props, dict):
            periods = props.get("periods")
            if isinstance(periods, list):
                return periods
            # Single observation/point -- return the properties object as one row
            return [props]
        for key in ("results", "data", "items"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def build_output(
    *, endpoint: str, raw: Any, params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dataset_ref": "usgov_noaa_nws",
        "endpoint": endpoint,
        "params": params,
        "rows": _extract_rows(raw),
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
