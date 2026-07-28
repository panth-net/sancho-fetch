from __future__ import annotations

from typing import Any, Protocol

from sancho.runtime.contracts import ModuleContext


class ModuleEntrypoint(Protocol):
    def __call__(self, *, context: ModuleContext, payload: dict[str, Any]) -> Any: ...
