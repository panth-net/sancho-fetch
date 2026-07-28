"""Phase 6 soft validation: emit warnings instead of hard failures.

Sancho should be lenient about *shape* mismatches (unknown provider params,
new API fields, catalog drift) so a correct AI/user request still runs.
Hard-block stays reserved for safety concerns: missing workspace, unsafe
paths, ``.env`` overwrite, corrupt cache, missing required API keys.
"""

from __future__ import annotations

from typing import Any


def soft_validate_schema(
    payload: Any,
    schema: dict[str, Any] | None,
    *,
    label: str = "payload",
) -> list[str]:
    """Validate ``payload`` against ``schema`` and return warning strings.

    Replaces ``validate_schema`` for non-safety checks: type mismatches and
    missing required fields are reported as warnings, not exceptions.
    """
    warnings: list[str] = []
    if not schema:
        return warnings

    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(payload, dict):
        warnings.append(f"{label} expected an object, got {type(payload).__name__}")
    elif expected_type == "array" and not isinstance(payload, list):
        warnings.append(f"{label} expected an array, got {type(payload).__name__}")

    if isinstance(payload, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in payload]
        if missing:
            warnings.append(
                f"{label} missing declared field(s): {', '.join(missing)} "
                "(soft warning -- module may still run via pass-through params)"
            )

        properties = schema.get("properties")
        if isinstance(properties, dict):
            declared = set(properties.keys())
            extras = sorted(set(payload.keys()) - declared)
            if extras:
                warnings.append(
                    f"{label} contains undeclared field(s): {', '.join(extras)} "
                    "(allowed -- passed through to the provider)"
                )
    return warnings


def required_env_keys(manifest: dict[str, Any]) -> list[str]:
    """Read ``api_key_env`` (str or list[str]) from a module manifest."""
    declared = manifest.get("api_key_env")
    if declared is None:
        return []
    if isinstance(declared, str):
        return [declared] if declared.strip() else []
    if isinstance(declared, list):
        return [str(item).strip() for item in declared if isinstance(item, str) and item.strip()]
    return []


def missing_required_keys(manifest: dict[str, Any], env: dict[str, str]) -> list[str]:
    """Return the env keys declared as required but absent/empty in ``env``."""
    return [name for name in required_env_keys(manifest) if not env.get(name)]
