"""Low-level save/load helpers for a single fetched-data cache record.

A record is one ``<timestamp>/`` directory holding ``data.json``,
``request.yml``, ``provenance.yml``, ``content.sha256`` and ``README.md``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from sancho.templates.runtime.cache_index import (
    DATA_FILE,
    HASH_FILE,
    PROVENANCE_FILE,
    README_FILE,
    REQUEST_FILE,
    append_jsonl_event,
    catalog_dir,
    regenerate_indexes,
    render_readme,
)
from sancho.templates.runtime.cache_policy import parse_age_seconds


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


def _read_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _write_yaml(path: Path, payload: Any) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def retention_settings(storage: Any) -> tuple[int, int] | None:
    if not isinstance(storage, dict):
        return None
    retention = storage.get("retention")
    if not isinstance(retention, dict) or not retention:
        return None
    try:
        keep_last_n = int(retention.get("keep_last_n", 0) or 0)
    except (TypeError, ValueError):
        keep_last_n = 0
    try:
        max_age_days = int(retention.get("max_age_days", 0) or 0)
    except (TypeError, ValueError):
        max_age_days = 0
    if keep_last_n <= 0 and max_age_days <= 0:
        return None
    return keep_last_n, max_age_days


def prune_if_configured(target_dir: Path, storage: Any) -> None:
    effective = storage
    if effective is None:
        try:
            from sancho.runtime import request_state as _request_state
            effective = _request_state.get_storage()
        except Exception:
            effective = None
    settings = retention_settings(effective)
    if settings is None:
        return
    keep_last_n, max_age_days = settings
    try:
        from sancho.catalog_cache import prune_raw_snapshots

        prune_raw_snapshots(
            target_dir, keep_last_n=keep_last_n, max_age_days=max_age_days
        )
    except Exception:
        pass


def save_record(
    *,
    data_raw_path: Path,
    module_id: str,
    family: str,
    sanitize: callable,
    request_key: str,
    record_dir: Path,
    raw: Any,
    params: dict[str, Any] | None,
    source_url: str,
    fetched_at_dt: datetime,
    metadata_extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """Write one cache record to disk. Returns the on-disk provenance dict."""
    counter = 1
    base_dir = record_dir
    while record_dir.exists():
        record_dir = base_dir.with_name(f"{base_dir.name}_{counter}")
        counter += 1
    record_dir.mkdir(parents=True, exist_ok=True)

    data_path = record_dir / DATA_FILE
    data_text = json.dumps(raw, indent=2, default=str, sort_keys=False)
    content_sha256 = hashlib.sha256(data_text.encode("utf-8")).hexdigest()
    data_path.write_text(data_text, encoding="utf-8")
    data_bytes = data_path.stat().st_size

    record_id = f"{sanitize(module_id)}/{sanitize(family)}/{request_key}/{record_dir.name}"
    fetched_at_iso = fetched_at_dt.isoformat()

    _write_yaml(record_dir / REQUEST_FILE, {
        "module_id": module_id,
        "family": family,
        "request_key": request_key,
        "params": params or {},
        "source_url": source_url or "",
    })

    provenance: dict[str, Any] = {
        "record_id": record_id,
        "module_id": module_id,
        "family": family,
        "request_key": request_key,
        "fetched_at": fetched_at_iso,
        "source_url": source_url or "",
        "content_sha256": content_sha256,
        "data_file": DATA_FILE,
        "data_bytes": data_bytes,
    }
    # Pick up module/sancho version from the executor's per-run thread-local.
    # Falls back to empty strings when called outside the executor (e.g. tests).
    try:
        from sancho.runtime import request_state as _request_state
        run_prov = _request_state.get_run_provenance()
    except Exception:
        run_prov = {}
    for key in ("module_version", "sancho_version", "module_source", "module_path"):
        provenance[key] = run_prov.get(key, "")
    if metadata_extra:
        for key, value in metadata_extra.items():
            if key not in provenance:
                provenance[key] = value
    _write_yaml(record_dir / PROVENANCE_FILE, provenance)

    (record_dir / HASH_FILE).write_text(
        f"sha256:{content_sha256}  {DATA_FILE}\n", encoding="utf-8"
    )
    (record_dir / README_FILE).write_text(
        render_readme(
            module_id=module_id,
            family=family,
            request_key=request_key,
            fetched_at_iso=fetched_at_iso,
            source_url=source_url or "",
            params=params or {},
            content_sha256=content_sha256,
            data_bytes=data_bytes,
            record_id=record_id,
        ),
        encoding="utf-8",
    )

    append_jsonl_event(
        catalog_dir(Path(data_raw_path)),
        {"ts": _utc_now().isoformat(), "event": "save", **provenance},
    )
    try:
        regenerate_indexes(Path(data_raw_path))
    except Exception:
        pass

    return {"record_dir": record_dir, "provenance": provenance, "data_path": data_path}


def load_record_from_dir(record_dir: Path) -> dict[str, Any] | None:
    """Load the parsed payload + metadata for a single record dir."""
    data_path = record_dir / DATA_FILE
    prov_path = record_dir / PROVENANCE_FILE
    if not data_path.exists() or not prov_path.exists():
        return None
    try:
        metadata = _read_yaml(prov_path)
    except Exception:
        return None
    if not isinstance(metadata, dict):
        return None
    request_payload: dict[str, Any] = {}
    request_path = record_dir / REQUEST_FILE
    if request_path.exists():
        try:
            request_payload = _read_yaml(request_path)
        except Exception:
            request_payload = {}
    enriched = dict(metadata)
    if "params" not in enriched:
        enriched["params"] = request_payload.get("params", {})
    try:
        raw_payload = json.loads(data_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "raw": raw_payload,
        "metadata": enriched,
        "data_path": data_path,
        "prov_path": prov_path,
        "record_dir": record_dir,
    }


def find_latest_record(
    *,
    family_dir: Path,
    request_key: str | None,
    max_age_seconds: int | float | str | None,
    now: datetime | None,
) -> Path | None:
    parsed_age = parse_age_seconds(max_age_seconds)
    if parsed_age is None or parsed_age <= 0:
        return None
    if not family_dir.exists():
        return None

    current_time = now.astimezone(timezone.utc) if isinstance(now, datetime) else _utc_now()

    if request_key is not None:
        target = family_dir / request_key
        if not target.exists():
            return None
        key_dirs: list[Path] = [target]
    else:
        key_dirs = [p for p in family_dir.iterdir() if p.is_dir()]

    candidates: list[tuple[datetime, Path]] = []
    for key_dir in key_dirs:
        for ts_dir in key_dir.iterdir():
            if not ts_dir.is_dir():
                continue
            prov_path = ts_dir / PROVENANCE_FILE
            if not prov_path.exists():
                continue
            try:
                meta = _read_yaml(prov_path)
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            fetched_at_raw = meta.get("fetched_at")
            fetched_at_dt = (
                _coerce_iso8601(fetched_at_raw)
                if isinstance(fetched_at_raw, str)
                else None
            )
            if fetched_at_dt is None:
                fetched_at_dt = datetime.fromtimestamp(prov_path.stat().st_mtime, tz=timezone.utc)
            if (current_time - fetched_at_dt).total_seconds() > parsed_age:
                continue
            candidates.append((fetched_at_dt, ts_dir))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]
