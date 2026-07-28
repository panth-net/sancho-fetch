from typing import Any

from sancho.runtime.contracts import ModuleContext, ModuleRunResult
from sancho.runtime.data_store import RawCacheRecord, load_raw, resolve_staleness_seconds, save_raw
from sancho.runtime.errors import SanchoError, ModuleExecutionError, SchemaValidationError, WorkspaceError
from sancho.runtime.schema import validate_schema
from sancho.runtime.transform_rows import extract_rows

# http and net drag in `requests` (~190ms); resolve them lazily so importing
# light runtime pieces (redaction, contracts) stays cheap for trivial commands.
_LAZY_EXPORTS = {
    "HttpClient": "sancho.runtime.http",
    "DownloadResult": "sancho.runtime.net",
    "download_file": "sancho.runtime.net",
    "get_json": "sancho.runtime.net",
}

__all__ = [
    "SanchoError",
    "ModuleExecutionError",
    "SchemaValidationError",
    "WorkspaceError",
    "ModuleContext",
    "ModuleRunResult",
    "RawCacheRecord",
    "HttpClient",
    "DownloadResult",
    "download_file",
    "get_json",
    "extract_rows",
    "save_raw",
    "load_raw",
    "resolve_staleness_seconds",
    "validate_schema",
]


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'sancho.runtime' has no attribute '{name}'")
    import importlib

    return getattr(importlib.import_module(module_name), name)
