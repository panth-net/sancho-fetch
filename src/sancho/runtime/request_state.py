"""Thread-local per-request state for the MCP runtime.

This bridges two layers without changing function signatures across the
codebase:

1. The HTTP/stdio handler layer (`sancho.mcp.server._HttpHandler.do_POST`) parses
   per-request runtime flags and stashes them here.
2. The executor / data-store layer reads it when running a module -- provider
   keys get merged into `ModuleContext.env` for that single request, and
   `save_raw` short-circuits into an in-memory record when stateless.

Storage is `threading.local()` so per-request state never leaks across
concurrent requests handled by `ThreadingHTTPServer`. The hosting wrapper is
responsible for calling `clear()` in a `finally:` at the end of every request.

Local / stdio / non-hosted use paths leave `stateless` false, so the rest
of Sancho Fetch behaves exactly as before.
"""

from __future__ import annotations

import threading
from typing import Any

_tls = threading.local()


def set_stateless(value: bool) -> None:
    _tls.stateless = bool(value)


def is_stateless() -> bool:
    return bool(getattr(_tls, "stateless", False))


def set_storage(storage: dict[str, Any] | None) -> None:
    _tls.storage = dict(storage) if isinstance(storage, dict) else None


def get_storage() -> dict[str, Any] | None:
    value = getattr(_tls, "storage", None)
    return dict(value) if isinstance(value, dict) else None


def set_run_provenance(
    *,
    module_version: str | None = None,
    sancho_version: str | None = None,
    module_source: str | None = None,
    module_path: str | None = None,
) -> None:
    _tls.run_provenance = {
        "module_version": module_version or "",
        "sancho_version": sancho_version or "",
        "module_source": module_source or "",
        "module_path": module_path or "",
    }


def get_run_provenance() -> dict[str, str]:
    value = getattr(_tls, "run_provenance", None)
    return dict(value) if isinstance(value, dict) else {}


# --- per-run cache record tracking -------------------------------------------
# The data store appends here as it writes (save_raw) or reuses (load_raw) a
# record, so the executor can surface the exact record dirs and cache hit/miss
# on ``ModuleRunResult`` without guessing "latest record for module".


def reset_run_records() -> None:
    _tls.records_saved = []
    _tls.records_reused = []
    _tls.pending_original = None


def note_record_saved(record_dir: Any) -> None:
    saved = getattr(_tls, "records_saved", None)
    if not isinstance(saved, list):
        saved = []
        _tls.records_saved = saved
    saved.append(str(record_dir))


def note_record_reused(record_dir: Any) -> None:
    reused = getattr(_tls, "records_reused", None)
    if not isinstance(reused, list):
        reused = []
        _tls.records_reused = reused
    reused.append(str(record_dir))


def get_run_records() -> dict[str, list[str]]:
    saved = getattr(_tls, "records_saved", None)
    reused = getattr(_tls, "records_reused", None)
    return {
        "saved": list(saved) if isinstance(saved, list) else [],
        "reused": list(reused) if isinstance(reused, list) else [],
    }


def summarize_run_records() -> tuple[list[str], str]:
    """Return ``(record_dirs, cache_status)`` for the run just executed.

    ``cache_status`` is ``"fetched_api"`` when anything was saved, else
    ``"reused_cache"`` when something was reused, else ``""``. Record dirs
    prefer freshly-saved over reused, de-duplicated and order-preserving.
    """
    records = get_run_records()
    saved, reused = records["saved"], records["reused"]
    cache_status = "fetched_api" if saved else ("reused_cache" if reused else "")
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in [*saved, *reused]:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered, cache_status


# --- pending original artifact -----------------------------------------------
# When a module downloads a real file (via net.download_file or by reading raw
# bytes), it records it here. The next save_raw auto-attaches it so the cache
# keeps the original byte-for-byte -- no per-module wiring of save_raw needed.


def note_pending_original(
    *,
    data: Any = None,
    path: Any = None,
    filename: str | None = None,
    media_type: str | None = None,
) -> None:
    _tls.pending_original = {
        "data": data,
        "path": str(path) if path is not None else None,
        "filename": filename,
        "media_type": media_type,
    }


def take_pending_original() -> dict[str, Any] | None:
    value = getattr(_tls, "pending_original", None)
    _tls.pending_original = None
    return dict(value) if isinstance(value, dict) else None


def clear() -> None:
    _tls.stateless = False
    _tls.storage = None
    _tls.run_provenance = None
    _tls.records_saved = []
    _tls.records_reused = []
    _tls.pending_original = None


__all__ = [
    "set_stateless",
    "is_stateless",
    "set_storage",
    "get_storage",
    "set_run_provenance",
    "get_run_provenance",
    "reset_run_records",
    "note_record_saved",
    "note_record_reused",
    "get_run_records",
    "summarize_run_records",
    "note_pending_original",
    "take_pending_original",
    "clear",
]
