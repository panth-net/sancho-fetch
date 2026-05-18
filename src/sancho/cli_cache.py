"""CLI for ``sancho cache status / list / show``."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from sancho.templates.runtime.data_store import (
    CATALOG_DIRNAME,
    DATA_FILE,
    PROVENANCE_FILE,
    REQUEST_FILE,
    _compute_request_key,
    _family_dir,
    _request_key_dir,
    iter_cache_records,
)
from sancho.workspace import find_workspace_root


STATUS_CACHED = "cached"
STATUS_MISSING = "missing"
STATUS_STALE = "stale"
STATUS_CORRUPT = "corrupt"
STATUS_EMPTY_RESULT = "empty_result"


def _fetched_data_root(workspace_root: Path) -> Path:
    return workspace_root / "fetched-data"


def _resolve_workspace(workspace_arg: str) -> Path:
    return find_workspace_root(Path(workspace_arg).resolve())


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


def _classify_record(record_dir: Path, max_age_seconds: int | None, now: datetime) -> str:
    prov_path = record_dir / PROVENANCE_FILE
    data_path = record_dir / DATA_FILE
    if not prov_path.exists() or not data_path.exists():
        return STATUS_CORRUPT
    try:
        prov = yaml.safe_load(prov_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return STATUS_CORRUPT
    if not isinstance(prov, dict):
        return STATUS_CORRUPT
    # Hash check
    expected = str(prov.get("content_sha256") or "")
    actual = hashlib.sha256(data_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    if expected and expected != actual:
        return STATUS_CORRUPT
    # Empty payload check
    try:
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    except Exception:
        return STATUS_CORRUPT
    if payload in (None, [], {}, ""):
        return STATUS_EMPTY_RESULT
    # Freshness check
    if max_age_seconds is not None:
        fetched_at_raw = prov.get("fetched_at")
        fetched_at = _coerce_iso8601(fetched_at_raw) if isinstance(fetched_at_raw, str) else None
        if fetched_at and (now - fetched_at).total_seconds() > max_age_seconds:
            return STATUS_STALE
    return STATUS_CACHED


def _list_timestamps(request_key_dir: Path) -> list[Path]:
    if not request_key_dir.exists():
        return []
    return sorted([p for p in request_key_dir.iterdir() if p.is_dir()], reverse=True)


def _load_request_file(request_file: Path) -> dict[str, Any]:
    if not request_file.exists():
        raise FileNotFoundError(f"request file does not exist: {request_file}")
    payload = yaml.safe_load(request_file.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"request file is not a YAML mapping: {request_file}")
    return payload


def _load_request_json(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--request-json must be a JSON object")
    return payload


def _status_for_request(
    workspace_root: Path,
    module_id: str,
    request_payload: dict[str, Any],
    max_age_seconds: int | None,
) -> dict[str, Any]:
    family = str(request_payload.get("family") or "")
    params = request_payload.get("params") or {}
    source_url = request_payload.get("source_url") or ""
    if not family:
        return {
            "module_id": module_id,
            "status": STATUS_MISSING,
            "detail": "request.yml is missing 'family'",
            "cached_units": 0,
            "missing_units": 1,
            "requested_units": 1,
        }
    request_key = _compute_request_key(params, source_url)
    rk_dir = _request_key_dir(_fetched_data_root(workspace_root), module_id, family, request_key)
    timestamps = _list_timestamps(rk_dir)
    if not timestamps:
        return {
            "module_id": module_id,
            "family": family,
            "request_key": request_key,
            "status": STATUS_MISSING,
            "requested_units": 1,
            "cached_units": 0,
            "missing_units": 1,
            "stale_units": 0,
            "corrupt_units": 0,
            "empty_units": 0,
        }
    now = datetime.now(timezone.utc)
    status = _classify_record(timestamps[0], max_age_seconds, now)
    return {
        "module_id": module_id,
        "family": family,
        "request_key": request_key,
        "status": status,
        "record_dir": str(timestamps[0]),
        "requested_units": 1,
        "cached_units": 1 if status == STATUS_CACHED else 0,
        "missing_units": 0,
        "stale_units": 1 if status == STATUS_STALE else 0,
        "corrupt_units": 1 if status == STATUS_CORRUPT else 0,
        "empty_units": 1 if status == STATUS_EMPTY_RESULT else 0,
        "history_count": len(timestamps),
    }


def _status_for_module(
    workspace_root: Path, module_id: str, max_age_seconds: int | None
) -> dict[str, Any]:
    root = _fetched_data_root(workspace_root)
    rows = [r for r in iter_cache_records(root) if r.get("module_id") == module_id]
    counts = {
        "cached_units": 0,
        "stale_units": 0,
        "corrupt_units": 0,
        "empty_units": 0,
    }
    now = datetime.now(timezone.utc)
    seen_keys: dict[str, str] = {}
    per_record: list[dict[str, Any]] = []
    for row in rows:
        record_dir = Path(row["record_dir"])
        status = _classify_record(record_dir, max_age_seconds, now)
        per_record.append({**row, "status": status})
        if status == STATUS_CACHED:
            counts["cached_units"] += 1
        elif status == STATUS_STALE:
            counts["stale_units"] += 1
        elif status == STATUS_CORRUPT:
            counts["corrupt_units"] += 1
        elif status == STATUS_EMPTY_RESULT:
            counts["empty_units"] += 1
        seen_keys[row["request_key"]] = status
    return {
        "module_id": module_id,
        "record_count": len(rows),
        "distinct_request_keys": len(seen_keys),
        **counts,
        "records": per_record,
    }


def cmd_cache_status(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    max_age = int(args.max_age_seconds) if args.max_age_seconds is not None else None
    if args.request_file and args.request_json:
        raise ValueError("Use only one of --request-file or --request-json")
    if args.request_file:
        payload = _load_request_file(Path(args.request_file).resolve())
        result = _status_for_request(workspace_root, args.module, payload, max_age)
    elif args.request_json:
        payload = _load_request_json(args.request_json)
        result = _status_for_request(workspace_root, args.module, payload, max_age)
    else:
        result = _status_for_module(workspace_root, args.module, max_age)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
        return 0

    print(f"Module: {result['module_id']}")
    if "family" in result:
        print(f"Family: {result['family']}")
        print(f"Request key: {result.get('request_key', '')}")
        print(f"Status: {result['status']}")
        print(
            f"Counts: cached={result['cached_units']} "
            f"missing={result['missing_units']} stale={result['stale_units']} "
            f"corrupt={result['corrupt_units']} empty={result['empty_units']}"
        )
        if "record_dir" in result:
            print(f"Record: {result['record_dir']}")
        print(f"History entries for this request_key: {result.get('history_count', 0)}")
    else:
        print(f"Records: {result['record_count']} across {result['distinct_request_keys']} request key(s).")
        print(
            f"Counts: cached={result['cached_units']} "
            f"stale={result['stale_units']} corrupt={result['corrupt_units']} "
            f"empty={result['empty_units']}"
        )
    return 0


def cmd_cache_list(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    root = _fetched_data_root(workspace_root)
    rows = iter_cache_records(root)
    if args.module:
        rows = [r for r in rows if r.get("module_id") == args.module]

    if getattr(args, "json", False):
        print(json.dumps({"records": rows, "count": len(rows)}, indent=2, default=str))
        return 0

    if not rows:
        print("No cached records.")
        return 0
    print(f"{len(rows)} cached record(s):")
    for row in rows:
        print(
            f"- {row['record_id']}  ({row.get('data_bytes', 0)} bytes, "
            f"{row.get('fetched_at', '?')})"
        )
    print()
    print(f"Catalog: {root / CATALOG_DIRNAME}")
    return 0


def _find_record_by_id(workspace_root: Path, record_id: str) -> Path | None:
    root = _fetched_data_root(workspace_root)
    # Accept either full record_id "module/family/key/timestamp" or just a key.
    parts = record_id.strip("/").split("/")
    if len(parts) == 4:
        candidate = root / parts[0] / parts[1] / parts[2] / parts[3]
        return candidate if candidate.exists() else None
    if len(parts) == 1:
        target = parts[0]
        for row in iter_cache_records(root):
            if row["request_key"] == target or row["record_id"].endswith(target):
                return Path(row["record_dir"])
    return None


def cmd_cache_show(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace(args.workspace)
    record_dir = _find_record_by_id(workspace_root, args.record_id)
    if record_dir is None:
        print(f"No cache record matched: {args.record_id}", file=sys.stderr)
        return 1
    prov = yaml.safe_load((record_dir / PROVENANCE_FILE).read_text(encoding="utf-8")) or {}
    req_path = record_dir / REQUEST_FILE
    req = yaml.safe_load(req_path.read_text(encoding="utf-8")) if req_path.exists() else {}

    if getattr(args, "json", False):
        print(json.dumps({"record_dir": str(record_dir), "provenance": prov, "request": req}, indent=2, default=str))
        return 0

    print(f"Record dir: {record_dir}")
    print(f"Record id:  {prov.get('record_id', '')}")
    print(f"Fetched at: {prov.get('fetched_at', '')}")
    print(f"Source URL: {prov.get('source_url', '')}")
    print(f"Bytes:      {prov.get('data_bytes', 0)}")
    print(f"SHA-256:    {prov.get('content_sha256', '')}")
    if isinstance(req, dict) and req.get("params"):
        print("Params:")
        print(yaml.safe_dump(req.get("params") or {}, sort_keys=False).rstrip())
    return 0


def add_cache_subcommands(subparsers: argparse._SubParsersAction) -> None:
    cache = subparsers.add_parser("cache", help="Inspect the fetched-data cache")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)

    status = cache_sub.add_parser("status", help="Report cache status for a module or request")
    status.add_argument("--module", required=True, help="Module id (e.g. fetch.census.acs_profile)")
    status.add_argument("--request-file", help="Optional request.yml describing a single request")
    status.add_argument("--request-json", help="Optional JSON object describing a single request")
    status.add_argument("--max-age-seconds", help="Max age (seconds) before a record is 'stale'")
    status.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    status.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    status.set_defaults(func=cmd_cache_status)

    listc = cache_sub.add_parser("list", help="List every cached record")
    listc.add_argument("--module", help="Filter to records for this module id")
    listc.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    listc.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    listc.set_defaults(func=cmd_cache_list)

    show = cache_sub.add_parser("show", help="Show details of a single cache record")
    show.add_argument("record_id", help="Record id (module/family/key/timestamp) or a request key")
    show.add_argument("--workspace", default=".", help="Project path containing sancho-workspace/")
    show.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    show.set_defaults(func=cmd_cache_show)
