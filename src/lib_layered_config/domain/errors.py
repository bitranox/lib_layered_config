"""Domain error taxonomy shared across layers.

Codifies the error classes referenced throughout ``docs/systemdesign`` so the
application and adapter layers can communicate failures without depending on
concrete implementations.

Contents:
    - ``ConfigError``: base class for every library-specific exception.
    - ``InvalidFormatError``: raised when structured configuration cannot be parsed.
    - ``ValidationError``: reserved for semantic validation of configuration
      payloads once implemented.
    - ``NotFoundError``: indicates optional configuration sources were absent.

System Role:
    Adapters raise these exceptions; the composition root and CLI translate them
    into operator-facing messages without leaking implementation details.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "InvalidFormatError",
    "ValidationError",
    "NotFoundError",
]


class ConfigError(Exception):
    """Base class for all configuration-related errors in the library.

    Centralises exception handling so callers can catch a single type when
    operating at library boundaries.
    """


class InvalidFormatError(ConfigError):
    """Raised when a configuration source cannot be parsed.

    Typical sources include malformed TOML, JSON, YAML, or dotenv files. The
    message should reference the offending path for operator debugging.
    """


class ValidationError(ConfigError, ValueError):
    """Raised when an identifier or platform value fails validation.

    Subclasses both :class:`ConfigError` (so a caller can catch every library error
    with a single ``except ConfigError``) and the stdlib :class:`ValueError` (so the
    long-standing ``except ValueError`` contract documented for the validation helpers
    keeps working). Raising this instead of a bare ``ValueError`` is backward compatible.
    """


class NotFoundError(ConfigError):
    """Indicates an optional configuration source was not discovered.

    Used when files, directory entries, or environment variable namespaces are
    genuinely missing; callers generally treat this as informational rather than
    fatal.
    """
