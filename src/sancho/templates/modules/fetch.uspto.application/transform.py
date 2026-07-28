
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _extract_rows(raw: Any) -> list[Any]:
    """Extract a list of rows from any USPTO ODP response envelope.

    The ODP uses "*Bag" keys for all list envelopes. We enumerate every known
    one so the same module can be pointed at any endpoint (applications,
    PTAB, petitions, bulk products, status codes) and still produce rows.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in (
            # Applications (PFW)
            "patentFileWrapperDataBag",
            # Nested per-application sub-bags (when endpoint returns only
            # assignment/continuity/etc. without the outer wrapper)
            "assignmentBag",
            "parentContinuityBag",
            "childContinuityBag",
            "foreignPriorityBag",
            "eventDataBag",
            "documents",
            "DocumentBag",
            # PTAB
            "proceedingBag",
            "patentTrialDecisionDataBag",
            "documentBag",
            # Petitions
            "petitionDecisionBag",
            "PetitionDecisionResponseBag",
            # Bulk datasets
            "bulkDataProductBag",
            "productFileBag",
            # Trademarks (future)
            "trademarkFileDataBag",
            # Generic fallbacks
            "results",
            "data",
            "Data",
            "items",
            "records",
            "observations",
            "hits",
        ):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def build_output(*, endpoint: str, raw: Any, params: dict[str, Any]) -> dict[str, Any]:
    rows = _extract_rows(raw)
    return {
        "dataset_ref": "usgov_uspto",
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "raw": raw,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
