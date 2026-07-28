from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _zip_filings(filings_recent: dict) -> list[dict]:
    """SEC's filings.recent is column-oriented -- each field is a parallel array.
    Zip them into row dicts: [{accessionNumber, filingDate, form, ...}, ...].
    """
    if not isinstance(filings_recent, dict):
        return []
    array_keys = [k for k, v in filings_recent.items() if isinstance(v, list)]
    if not array_keys:
        return []
    length = min(len(filings_recent[k]) for k in array_keys)
    rows: list[dict] = []
    for i in range(length):
        row = {k: filings_recent[k][i] for k in array_keys if i < len(filings_recent[k])}
        rows.append(row)
    return rows


def _extract_xbrl_facts(facts: dict) -> list[dict]:
    """companyfacts endpoint: facts.{taxonomy}.{tag}.units.{unit}[]."""
    rows: list[dict] = []
    if not isinstance(facts, dict):
        return rows
    for taxonomy, tags in facts.items():
        if not isinstance(tags, dict):
            continue
        for tag, body in tags.items():
            if not isinstance(body, dict):
                continue
            units = body.get("units") or {}
            if not isinstance(units, dict):
                continue
            for unit, observations in units.items():
                if not isinstance(observations, list):
                    continue
                for obs in observations:
                    if isinstance(obs, dict):
                        rows.append({**obs, "taxonomy": taxonomy, "tag": tag, "unit": unit})
    return rows


def _extract_xbrl_concept_units(raw: dict) -> list[dict]:
    """companyconcept endpoint: top-level `units.{unit}[]`."""
    rows: list[dict] = []
    units = raw.get("units") or {}
    if not isinstance(units, dict):
        return rows
    for unit, observations in units.items():
        if not isinstance(observations, list):
            continue
        for obs in observations:
            if isinstance(obs, dict):
                rows.append({**obs, "unit": unit})
    return rows


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    # SEC has 4 distinct response shapes by URL:
    # - /submissions/CIK*.json    -> filings.recent column arrays (zip)
    # - /api/xbrl/companyfacts/.. -> facts.{tax}.{tag}.units.{unit}[]
    # - /api/xbrl/companyconcept/.. -> units.{unit}[]
    # - /api/xbrl/frames/..       -> data[]
    rows: list = []
    if isinstance(raw, dict):
        if "filings" in raw and isinstance(raw["filings"], dict):
            rows = _zip_filings(raw["filings"].get("recent", {}))
        elif "facts" in raw:
            rows = _extract_xbrl_facts(raw["facts"])
        elif "units" in raw:
            rows = _extract_xbrl_concept_units(raw)
        elif isinstance(raw.get("data"), list):
            rows = raw["data"]
    return {
        "dataset_ref": "usgov_sec_filings",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
