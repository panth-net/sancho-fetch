from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

_STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"
_SIGN_API = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
_UA = "SanchoFetch/1.0 (sancho)"


def _sign_url(url: str, subscription_key: str | None) -> str:
    """Sign a blob URL via the Planetary Computer SAS endpoint."""
    if not url or "blob.core.windows.net" not in url:
        return url
    headers = {"User-Agent": _UA}
    if subscription_key:
        headers["Ocp-Apim-Subscription-Key"] = subscription_key
    resp = requests.get(_SIGN_API, params={"href": url}, headers=headers, timeout=30)
    if resp.ok:
        return resp.json().get("href", url)
    return url


def list_collections(
    *,
    runtime_http: dict[str, Any],
    subscription_key: str | None,
    limit: int,
) -> dict[str, Any]:
    timeout = float(runtime_http.get("timeout_seconds", 60))
    url = f"{_STAC_API}/collections"
    headers = {"User-Agent": _UA}
    if subscription_key:
        headers["Ocp-Apim-Subscription-Key"] = subscription_key

    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    collections = data.get("collections", [])[:limit]

    rows = []
    for c in collections:
        rows.append({
            "id": c.get("id", ""),
            "title": c.get("title", ""),
            "description": (c.get("description", "") or "")[:200],
            "license": c.get("license", ""),
            "temporal": c.get("extent", {}).get("temporal", {}).get("interval", []),
            "spatial": c.get("extent", {}).get("spatial", {}).get("bbox", []),
        })

    return {
        "source_url": url,
        "collection_count": len(rows),
        "rows": rows,
    }


def search_items(
    *,
    runtime_http: dict[str, Any],
    subscription_key: str | None,
    collection: str,
    bbox: list[float] | None,
    datetime_range: str | None,
    limit: int,
) -> dict[str, Any]:
    timeout = float(runtime_http.get("timeout_seconds", 60))
    url = f"{_STAC_API}/search"
    headers = {"User-Agent": _UA, "Content-Type": "application/json"}
    if subscription_key:
        headers["Ocp-Apim-Subscription-Key"] = subscription_key

    body: dict[str, Any] = {
        "collections": [collection],
        "limit": min(limit, 1000),
    }
    if bbox:
        body["bbox"] = bbox
    if datetime_range:
        body["datetime"] = datetime_range

    resp = requests.post(url, json=body, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])

    rows = []
    for f in features:
        props = f.get("properties", {})
        rows.append({
            "id": f.get("id", ""),
            "collection": collection,
            "datetime": props.get("datetime", ""),
            "created": props.get("created", ""),
            "platform": props.get("platform", ""),
            "cloud_cover": props.get("eo:cloud_cover"),
            "bbox": f.get("bbox"),
            "asset_count": len(f.get("assets", {})),
        })

    return {
        "source_url": url,
        "collection": collection,
        "matched": data.get("numberMatched", len(rows)),
        "rows": rows,
    }
