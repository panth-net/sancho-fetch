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


def clear() -> None:
    _tls.stateless = False
    _tls.storage = None
    _tls.run_provenance = None


__all__ = [
    "set_stateless",
    "is_stateless",
    "set_storage",
    "get_storage",
    "set_run_provenance",
    "get_run_provenance",
    "clear",
]
