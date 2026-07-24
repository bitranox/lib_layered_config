"""Pure domain logic for masking sensitive configuration values.

Provide a recursive redaction mechanism that replaces values associated with
sensitive key names (passwords, tokens, secrets, API keys) with a placeholder
string.  This prevents accidental exposure of secrets in logs, CLI output,
debug dumps, or JSON exports.

Contents:
    - ``REDACTED_PLACEHOLDER``: constant string used as the replacement value.
    - ``is_sensitive``: predicate testing whether a key name matches known
      sensitive patterns.
    - ``redact_mapping``: recursive function that creates a redacted copy of a
      configuration mapping.

System Role:
    Called by ``Config.to_json(redact=True)`` and ``Config.as_dict(redact=True)``
    to produce safe representations of configuration data.  Lives in the domain
    layer with no external dependencies (stdlib ``re`` only).
"""

from __future__ import annotations

import re
from typing import Any, Final, cast

from .errors import InvalidFormatError

__all__ = ["REDACTED_PLACEHOLDER", "is_sensitive", "redact_mapping"]

#: Maximum nesting depth for redaction. Guards against an opaque ``RecursionError`` on a
#: pathologically deep mapping passed to the public ``redact_mapping``.
_MAX_REDACT_DEPTH: Final[int] = 100

REDACTED_PLACEHOLDER: Final[str] = "***REDACTED***"
"""Constant replacing sensitive values in redacted output."""

_SENSITIVE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|_)(?:"
    r"password|passwd|passphrase|secret|token|credential|apikey|cookie|jwt|signature|session_id|sessionid"
    r")s?(?:_|$)"
    # `_key` requires a leading underscore so compound names (api_key, access_key,
    # aws_access_key_id, signing_key) match while a field literally named "key" - a
    # common non-secret map/identifier field - does not get swept up.
    r"|_key(?:s|_|$)",
    re.IGNORECASE,
)


def is_sensitive(key: str) -> bool:
    """Return ``True`` when *key* matches a known sensitive name pattern.

    Patterns are matched case-insensitively with underscore word boundaries.
    Supported stems include ``password``, ``passwd``, ``passphrase``, ``secret``,
    ``token``, ``credential``, ``apikey``, ``cookie``, ``jwt``, ``signature``, and
    ``session_id``, with optional plural suffix and prefix/suffix separated by
    underscores. A ``_key`` suffix also matches (``api_key`` / ``access_key`` /
    ``signing_key``), but a field literally named ``key`` does not, so benign names like
    ``keyboard``, ``monkey``, and a plain ``key`` map field are not treated as sensitive.

    Args:
        key: Configuration key name to test.

    Returns:
        Whether the key should be treated as sensitive.

    Examples:
        >>> is_sensitive("database_password")
        True
        >>> is_sensitive("api_token")
        True
        >>> is_sensitive("hostname")
        False
        >>> is_sensitive("monkey")
        False
    """
    return _SENSITIVE_PATTERN.search(key) is not None


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *data* with sensitive values replaced.

    Creates a new dictionary without mutating the input.  Recurses into nested
    dictionaries and lists of dictionaries to redact sensitive keys at any
    depth.

    Args:
        data: Configuration mapping to redact.

    Returns:
        New mapping with sensitive values replaced by ``REDACTED_PLACEHOLDER``.

    Examples:
        >>> redact_mapping({"password": "s3cret", "host": "localhost"})
        {'password': '***REDACTED***', 'host': 'localhost'}
        >>> original = {"db": {"password": "s3cret"}}
        >>> redact_mapping(original)
        {'db': {'password': '***REDACTED***'}}
        >>> original["db"]["password"]
        's3cret'
    """
    return _redact_dict(data)


def _redact_dict(mapping: dict[str, Any], _depth: int = 0) -> dict[str, Any]:
    """Recursively redact sensitive values in a dictionary.

    Args:
        mapping: Dictionary to process.
        _depth: Current recursion depth (internal).

    Returns:
        New dictionary with sensitive values replaced.

    Raises:
        InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
    """
    if _depth > _MAX_REDACT_DEPTH:
        raise InvalidFormatError(f"Configuration nesting exceeds the maximum depth of {_MAX_REDACT_DEPTH}")
    result: dict[str, Any] = {}
    for key, value in mapping.items():
        if is_sensitive(key):
            result[key] = REDACTED_PLACEHOLDER
        elif isinstance(value, dict):
            result[key] = _redact_dict(cast("dict[str, Any]", value), _depth + 1)
        elif isinstance(value, list):
            result[key] = _redact_list(cast("list[Any]", value), _depth + 1)
        else:
            result[key] = value
    return result


def _redact_list(items: list[Any], _depth: int = 0) -> list[Any]:
    """Recursively redact sensitive values within list items.

    Only dictionary items are recursed into; other list elements pass through.

    Args:
        items: List to process.
        _depth: Current recursion depth (internal).

    Returns:
        New list with sensitive values in nested dicts replaced.

    Raises:
        InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
    """
    if _depth > _MAX_REDACT_DEPTH:
        raise InvalidFormatError(f"Configuration nesting exceeds the maximum depth of {_MAX_REDACT_DEPTH}")
    result: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            result.append(_redact_dict(cast("dict[str, Any]", item), _depth + 1))
        else:
            result.append(item)
    return result
