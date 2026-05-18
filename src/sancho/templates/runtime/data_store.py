"""Source-shaped fetched-data cache: public save_raw/load_raw API.

Layout: ``fetched-data/<module>/<family>/<request_key>/<timestamp>/`` with
data.json, request.yml, provenance.yml, content.sha256, README.md. See
cache_record_io.py and cache_index.py for record write/read and the
``_catalog/`` index.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sancho.templates.runtime.cache_index import (
    CATALOG_DIRNAME,
    DATA_FILE,
    HASH_FILE,
    PROVENANCE_FILE,
    README_FILE,
    REQUEST_FILE,
    iter_cache_records,
)
from sancho.templates.runtime.cache_policy import (
    is_raw_cache_enabled,
    parse_age_seconds,
    resolve_staleness_seconds,
)
from sancho.templates.runtime.cache_record_io import (
    find_latest_record,
    load_record_from_dir,
    prune_if_configured,
    save_record,
)

DEFAULT_CACHE_MAX_AGE_SECONDS = 3600


@dataclass(frozen=True)
class RawCacheRecord:
    raw: Any
    metadata: dict[str, Any]
    raw_path: Path
    meta_path: Path
    record_dir: Path | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_iso8601(value: str) -> datetime | None:
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sanitize_segment(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return "default"
    safe = normalized.replace("\\", "_").replace("/", "_")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", safe)
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("._") or "default"


def _to_filename_timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _compute_request_key(params: Any, source_url: str | None) -> str:
    payload = {"params": params or {}, "source_url": source_url or ""}
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _family_dir(data_raw_path: Path, module_id: str, family: str) -> Path:
    return (
        Path(data_raw_path)
        / _sanitize_segment(module_id)
        / _sanitize_segment(family)
    )


def _request_key_dir(
    data_raw_path: Path, module_id: str, family: str, request_key: str
) -> Path:
    return _family_dir(data_raw_path, module_id, family) / request_key


def _record_dir(
    data_raw_path: Path,
    module_id: str,
    family: str,
    request_key: str,
    timestamp: datetime,
) -> Path:
    return _request_key_dir(data_raw_path, module_id, family, request_key) / _to_filename_timestamp(timestamp)


def _is_context(value: Any) -> bool:
    return hasattr(value, "data_raw_path")


def _require_non_empty_str(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _save_raw_record(
    *,
    data_raw_path: Path,
    module_id: str,
    family_or_dataset_id: str,
    raw: Any,
    params: dict[str, Any] | None,
    source_url: str,
    fetched_at: str | None,
    now: datetime | None,
    metadata_extra: dict[str, Any] | None = None,
    storage: Any = None,
) -> RawCacheRecord:
    now_utc = now.astimezone(timezone.utc) if isinstance(now, datetime) else _utc_now()
    parsed_fetched_at = _coerce_iso8601(fetched_at) if isinstance(fetched_at, str) else None
    fetched_at_dt = parsed_fetched_at or now_utc

    request_key = _compute_request_key(params, source_url)
    target_dir = _record_dir(
        data_raw_path, module_id, family_or_dataset_id, request_key, fetched_at_dt
    )
    result = save_record(
        data_raw_path=Path(data_raw_path),
        module_id=module_id,
        family=family_or_dataset_id,
        sanitize=_sanitize_segment,
        request_key=request_key,
        record_dir=target_dir,
        raw=raw,
        params=params,
        source_url=source_url,
        fetched_at_dt=fetched_at_dt,
        metadata_extra=metadata_extra,
    )
    provenance = result["provenance"]
    record_dir = result["record_dir"]
    data_path = result["data_path"]

    metadata = dict(provenance)
    metadata["params"] = params or {}

    prune_if_configured(
        _request_key_dir(Path(data_raw_path), module_id, family_or_dataset_id, request_key),
        storage,
    )

    return RawCacheRecord(
        raw=raw,
        metadata=metadata,
        raw_path=data_path,
        meta_path=record_dir / PROVENANCE_FILE,
        record_dir=record_dir,
    )


def save_raw(
    data_raw_path: Path | Any,
    module_id: str,
    family_or_dataset_id: str,
    raw: Any,
    params: dict[str, Any] | None = None,
    source_url: str | None = None,
    fetched_at: str | None = None,
    now: datetime | None = None,
) -> RawCacheRecord | Any:
    module_id_value = _require_non_empty_str("module_id", module_id)
    family_value = _require_non_empty_str("family_or_dataset_id", family_or_dataset_id)

    try:
        from sancho.runtime import request_state as _request_state
        if _request_state.is_stateless():
            return raw
    except Exception:
        pass

    if _is_context(data_raw_path):
        context_path = getattr(data_raw_path, "data_raw_path", None)
        if not isinstance(context_path, (str, Path)):
            raise TypeError("context.data_raw_path must be a filesystem path")

        meta = params if isinstance(params, dict) else {}
        params_obj = meta.get("params")
        params_payload = params_obj if isinstance(params_obj, dict) else {}
        source_url_value = str(source_url if source_url is not None else meta.get("source_url", ""))
        meta_fetched_at_obj = meta.get("fetched_at")
        meta_fetched_at = meta_fetched_at_obj if isinstance(meta_fetched_at_obj, str) else None
        fetched_at_value = fetched_at if isinstance(fetched_at, str) and fetched_at.strip() else meta_fetched_at
        metadata_extra = {
            key: value for key, value in meta.items()
            if key not in {"params", "source_url", "fetched_at"}
        }

        record = _save_raw_record(
            data_raw_path=Path(context_path),
            module_id=module_id_value,
            family_or_dataset_id=family_value,
            raw=raw,
            params=params_payload,
            source_url=source_url_value,
            fetched_at=fetched_at_value,
            now=now,
            metadata_extra=metadata_extra,
            storage=getattr(data_raw_path, "storage", None),
        )
        return record.raw

    if source_url is None:
        raise TypeError("source_url is required when data_raw_path is not a context object")

    return _save_raw_record(
        data_raw_path=Path(data_raw_path),
        module_id=module_id_value,
        family_or_dataset_id=family_value,
        raw=raw,
        params=params if isinstance(params, dict) else None,
        source_url=str(source_url),
        fetched_at=fetched_at,
        now=now,
    )


def _load_raw_record(
    *,
    data_raw_path: Path,
    module_id: str,
    family_or_dataset_id: str,
    params: dict[str, Any] | None,
    source_url: str | None,
    max_age_seconds: int | float | str | None,
    now: datetime | None = None,
) -> RawCacheRecord | None:
    family_dir = _family_dir(data_raw_path, module_id, family_or_dataset_id)
    request_key = (
        _compute_request_key(params, source_url)
        if (params is not None or source_url is not None)
        else None
    )
    record_dir = find_latest_record(
        family_dir=family_dir,
        request_key=request_key,
        max_age_seconds=max_age_seconds,
        now=now,
    )
    if record_dir is None:
        return None
    loaded = load_record_from_dir(record_dir)
    if loaded is None:
        return None
    return RawCacheRecord(
        raw=loaded["raw"],
        metadata=loaded["metadata"],
        raw_path=loaded["data_path"],
        meta_path=loaded["prov_path"],
        record_dir=loaded["record_dir"],
    )


def load_raw(
    data_raw_path: Path | Any,
    module_id: str,
    family_or_dataset_id: str,
    params: dict[str, Any] | int | float | str | None = None,
    source_url: str | None = None,
    max_age_seconds: int | float | str | None = None,
    now: datetime | None = None,
) -> RawCacheRecord | Any | None:
    module_id_value = _require_non_empty_str("module_id", module_id)
    family_value = _require_non_empty_str("family_or_dataset_id", family_or_dataset_id)

    if _is_context(data_raw_path):
        context_path = getattr(data_raw_path, "data_raw_path", None)
        if not isinstance(context_path, (str, Path)):
            raise TypeError("context.data_raw_path must be a filesystem path")
        context_max_age = max_age_seconds
        if context_max_age is None and not isinstance(params, dict):
            context_max_age = params
        record = _load_raw_record(
            data_raw_path=Path(context_path),
            module_id=module_id_value,
            family_or_dataset_id=family_value,
            params=None,
            source_url=None,
            max_age_seconds=context_max_age,
            now=now,
        )
        return None if record is None else record.raw

    return _load_raw_record(
        data_raw_path=Path(data_raw_path),
        module_id=module_id_value,
        family_or_dataset_id=family_value,
        params=params if isinstance(params, dict) else None,
        source_url=source_url if isinstance(source_url, str) else None,
        max_age_seconds=max_age_seconds,
        now=now,
    )
