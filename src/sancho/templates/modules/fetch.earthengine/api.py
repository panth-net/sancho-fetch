from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _init_ee(project: str | None) -> Any:
    try:
        import ee
    except ImportError:
        raise RuntimeError(
            "earthengine-api is not installed. Run: pip install earthengine-api\n"
            "Then authenticate: earthengine authenticate"
        )
    try:
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()
    except Exception as exc:
        raise RuntimeError(
            f"Earth Engine initialization failed: {exc}\n"
            "Run: earthengine authenticate"
        ) from exc
    return ee


def extract_raster_stats(
    *,
    project: str | None,
    dataset_id: str,
    bbox: list[float],
    bands: list[str] | None,
    reducer: str,
    date_start: str | None,
    date_end: str | None,
    scale: int,
) -> dict[str, Any]:
    ee = _init_ee(project)

    west, south, east, north = bbox
    aoi = ee.Geometry.Rectangle([west, south, east, north])

    image = ee.Image(dataset_id)
    if date_start or date_end:
        collection = ee.ImageCollection(dataset_id)
        if date_start:
            collection = collection.filterDate(date_start, date_end or "2099-12-31")
        image = collection.median()

    if bands:
        image = image.select(bands)

    reducer_fn = getattr(ee.Reducer, reducer, None)
    if reducer_fn is None:
        raise ValueError(f"Unknown reducer: {reducer}. Use: mean, median, sum, min, max, stdDev, count")

    result = image.reduceRegion(
        reducer=reducer_fn(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e9,
    )
    stats = result.getInfo()

    return {
        "source_url": f"earthengine://{dataset_id}",
        "dataset_id": dataset_id,
        "bbox": bbox,
        "reducer": reducer,
        "scale": scale,
        "stats": stats,
        "rows": [stats] if stats else [],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def extract_vector_features(
    *,
    project: str | None,
    dataset_id: str,
    bbox: list[float] | None,
    limit: int,
    properties: list[str] | None,
) -> dict[str, Any]:
    ee = _init_ee(project)

    fc = ee.FeatureCollection(dataset_id)

    if bbox:
        west, south, east, north = bbox
        aoi = ee.Geometry.Rectangle([west, south, east, north])
        fc = fc.filterBounds(aoi)

    fc = fc.limit(limit)

    if properties:
        fc = fc.select(properties)

    features = fc.getInfo()
    rows = []
    for f in features.get("features", []):
        row = dict(f.get("properties", {}))
        geom = f.get("geometry")
        if geom:
            row["_geometry_type"] = geom.get("type", "")
        rows.append(row)

    return {
        "source_url": f"earthengine://{dataset_id}",
        "dataset_id": dataset_id,
        "bbox": bbox,
        "feature_count": len(rows),
        "rows": rows,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
