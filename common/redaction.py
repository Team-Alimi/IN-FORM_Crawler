"""Redaction helpers for local runtime artifacts and status logs."""

from __future__ import annotations

import re

_SENSITIVE_FIELD_NAMES = {
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\s*([=:])\s*[^\s,;]+"
)
_POSTGRES_DSN_PATTERN = re.compile(r"(?i)(postgres(?:ql)?://[^:\s/]+:)[^@\s/]+@")


def sanitize_runtime_artifact(value):
    """Return a copy that omits known credential-bearing mapping fields."""
    if isinstance(value, dict):
        return {
            key: sanitize_runtime_artifact(item)
            for key, item in value.items()
            if isinstance(key, str) and key.lower() not in _SENSITIVE_FIELD_NAMES
        }
    if isinstance(value, list):
        return [sanitize_runtime_artifact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_runtime_artifact(item) for item in value)
    return value


def sanitize_log_message(message):
    """Remove common inline credential forms before a message reaches any handler."""
    redacted = _POSTGRES_DSN_PATTERN.sub(r"\1<redacted>@", str(message))
    return _ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>", redacted
    )
