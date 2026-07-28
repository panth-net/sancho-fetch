from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class MCPPolicy:
    fetch_only: bool = False
    allowlisted_module_ids: set[str] | None = None
    stateless: bool = False
    max_response_bytes: int = 0
    max_request_bytes: int = 0
    instructions: str | None = None
    nudge_footer: str | None = None


@dataclass
class MCPContext:
    workspace_root: Path
    policy: MCPPolicy = field(default_factory=MCPPolicy)
    quick_mode: bool = False
    quick_profile: str | None = None
    quick_targets: tuple[str, ...] = ()
    quick_modules: tuple[str, ...] = ()


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]


@dataclass
class FamilyAliasBinding:
    name: str
    provider: str
    module_id: str
    family_id: str
    method: str
    base: str
    path_template: str
    path_vars: tuple[str, ...]
