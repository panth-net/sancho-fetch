from __future__ import annotations

from typing import Any

from sancho.runtime.errors import SchemaValidationError


def validate_schema(payload: Any, schema: dict[str, Any] | None, *, label: str = "payload") -> None:
    if not schema:
        return

    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(payload, dict):
        raise SchemaValidationError(f"{label} must be an object")
    if expected_type == "array" and not isinstance(payload, list):
        raise SchemaValidationError(f"{label} must be an array")

    if isinstance(payload, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in payload]
        if missing:
            joined = ", ".join(missing)
            raise SchemaValidationError(f"{label} missing required fields: {joined}")
