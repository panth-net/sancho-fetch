from __future__ import annotations

import re
from typing import Any

_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)((?:[?&]|\b)(?:api[_-]?key|apikey|key|token|access_token|api_token)=)[^&\s`'\"}]+"
)
_SENSITIVE_JSON_RE = re.compile(
    r"(?i)(['\"](?:api[_-]?key|apikey|key|token|access_token|api_token)['\"]\s*:\s*['\"])[^'\"]+(['\"])",
)
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "key",
    "token",
    "access_token",
    "api_token",
    "authorization",
    "x-api-key",
}


def redact_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = _SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", text)
    return _SENSITIVE_JSON_RE.sub(r"\1[REDACTED]\2", redacted)


def redact_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _SENSITIVE_KEYS:
                out[key_text] = "[REDACTED]"
            else:
                out[key_text] = redact_sensitive_payload(item)
        return out
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value) or value
    return value
