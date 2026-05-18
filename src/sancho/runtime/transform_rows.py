"""Shared row extraction from heterogeneous API response shapes.

Most fetch APIs return either:
- A plain list of records: ``[{...}, {...}]``
- A dict envelope with the records under a known key:
  ``{"results": [...], "count": N}``, ``{"rows": [...]}``, etc.

This module provides ``extract_rows()`` so every transform uses the same
logic and placeholder patterns like ``rows = raw if isinstance(raw, list) else []``
don't silently drop real data.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_KEYS: tuple[str, ...] = (
    "results", "rows", "data", "items", "records", "observations",
    "features", "bills", "studies", "awards", "entries", "datasets",
    "documents", "hits",
)


def _resolve_path(raw: dict, path: str) -> Any:
    """Walk a dotted path through nested dicts (e.g. 'hits.hits' or 'Results.Facilities')."""
    current: Any = raw
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def extract_rows(
    raw: Any,
    *,
    preferred_keys: tuple[str, ...] | None = None,
    fallback_to_single: bool = False,
    unwrap_source: bool = False,
) -> list[Any]:
    """Extract a list of row-dicts from a variety of API response shapes.

    Parameters
    ----------
    preferred_keys:
        Module-specific envelope keys to try first. Supports dotted paths
        like ``"hits.hits"`` or ``"Results.Facilities"``.
    fallback_to_single:
        If no list is found, return ``[raw]`` (treat the dict as a single row).
    unwrap_source:
        For Elasticsearch-style responses at preferred_keys, unwrap each row's
        ``_source`` key.

    Order of resolution:
    1. If ``raw`` is already a list, return it directly.
    2. If ``raw`` is a dict:
       a. Try ``preferred_keys`` (supports nested dotted paths).
       b. Try ``_DEFAULT_KEYS`` common envelope names.
       c. Auto-detect Elasticsearch envelope: ``hits.hits[*]._source``.
       d. If the dict has exactly one list value, use that list.
       e. If ``fallback_to_single=True``, return ``[raw]``.
    3. Otherwise, return ``[]``.
    """
    if isinstance(raw, list):
        return raw

    if not isinstance(raw, dict):
        return []

    if preferred_keys:
        for key in preferred_keys:
            value = _resolve_path(raw, key) if "." in key else raw.get(key)
            if isinstance(value, list):
                if unwrap_source:
                    return [h["_source"] for h in value if isinstance(h, dict) and "_source" in h]
                return value

    for key in _DEFAULT_KEYS:
        value = raw.get(key)
        if isinstance(value, list):
            return value

    # Auto-detect Elasticsearch envelope
    hits_outer = raw.get("hits")
    if isinstance(hits_outer, dict):
        hits_inner = hits_outer.get("hits")
        if isinstance(hits_inner, list):
            return [h["_source"] for h in hits_inner if isinstance(h, dict) and "_source" in h]

    # Unique-list-value heuristic
    list_values = [v for v in raw.values() if isinstance(v, list)]
    if len(list_values) == 1:
        return list_values[0]

    if fallback_to_single:
        return [raw]

    return []


__all__ = ["extract_rows"]
