from __future__ import annotations

from typing import Any

S3_BASE = "s3://overturemaps-us-west-2/release/{release}/theme={theme}/type=*/*"
AZURE_BASE = "https://overturemapswestus2.blob.core.windows.net/release/{release}/theme={theme}/type=*/*"
VALID_THEMES = {"addresses", "buildings", "places", "transportation", "base", "divisions"}


def build_source_url(*, release: str, theme: str) -> str:
    return S3_BASE.format(release=release, theme=theme)


def fetch_overture(
    *,
    runtime_http: dict[str, Any],
    bbox: list[float],
    theme: str,
    release: str,
    limit: int,
) -> dict[str, Any]:
    if theme not in VALID_THEMES:
        raise ValueError(f"Invalid theme '{theme}'. Must be one of: {', '.join(sorted(VALID_THEMES))}")
    if len(bbox) != 4:
        raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat]")

    min_lon, min_lat, max_lon, max_lat = bbox
    source_url = build_source_url(release=release, theme=theme)

    try:
        import duckdb
    except ImportError:
        raise RuntimeError(
            "Overture Maps requires DuckDB. Install with: pip install duckdb\n"
            "Then install spatial extension: INSTALL spatial; LOAD spatial;"
        )

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")

    query = f"""
    SELECT * FROM read_parquet('{source_url}', hive_partitioning=1)
    WHERE bbox.xmin >= {min_lon}
      AND bbox.ymin >= {min_lat}
      AND bbox.xmax <= {max_lon}
      AND bbox.ymax <= {max_lat}
    LIMIT {limit}
    """

    try:
        result = con.execute(query)
        columns = [desc[0] for desc in result.description]
        raw_rows = result.fetchall()
        rows = [dict(zip(columns, row)) for row in raw_rows]
    except Exception as exc:
        # Fallback: return error with instructions
        return {
            "source_url": source_url,
            "error": str(exc),
            "instructions": "Overture Maps query failed. Ensure DuckDB spatial extension is installed.",
            "rows": [],
            "row_count": 0,
        }
    finally:
        con.close()

    # Serialize DuckDB types to JSON-safe values
    safe_rows = []
    for row in rows:
        safe = {}
        for k, v in row.items():
            if isinstance(v, (dict, list, str, int, float, bool)) or v is None:
                safe[k] = v
            else:
                safe[k] = str(v)
        safe_rows.append(safe)

    return {
        "source_url": source_url,
        "theme": theme,
        "release": release,
        "bbox": bbox,
        "rows": safe_rows,
        "row_count": len(safe_rows),
    }
