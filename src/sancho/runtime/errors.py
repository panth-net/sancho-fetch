from __future__ import annotations


class SanchoError(Exception):
    """Base Sancho Fetch runtime exception."""


class ModuleExecutionError(SanchoError):
    """Raised when a module fails during execution."""


class SchemaValidationError(SanchoError):
    """Raised when runtime schema validation fails."""


class WorkspaceError(SanchoError):
    """Raised when workspace structure is invalid."""
