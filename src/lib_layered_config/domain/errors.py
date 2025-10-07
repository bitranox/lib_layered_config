"""Domain error taxonomy shared across layers.

Purpose
-------
 codifies the error classes referenced throughout ``docs/systemdesign`` so the
application and adapter layers can communicate failures without depending on
concrete implementations.

Contents
--------
- ``ConfigError``: base class for every library-specific exception.
- ``InvalidFormat``: raised when structured configuration cannot be parsed.
- ``ValidationError``: reserved for semantic validation of configuration
  payloads once implemented.
- ``NotFound``: indicates optional configuration sources were absent.

System Role
-----------
Adapters raise these exceptions; the composition root and CLI translate them
into operator-facing messages without leaking implementation details.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "InvalidFormat",
    "ValidationError",
    "NotFound",
]


class ConfigError(Exception):
    """Base class for all configuration-related errors in the library.

    Why
    ----
    Centralises exception handling so callers can catch a single type when
    operating at library boundaries.
    """


class InvalidFormat(ConfigError):
    """Raised when a configuration source cannot be parsed.

    Typical sources include malformed TOML, JSON, YAML, or dotenv files. The
    message should reference the offending path for operator debugging.
    """


class ValidationError(ConfigError):
    """Placeholder for semantic configuration validation failures.

    The current release does not perform semantic validation, but the class is
    reserved so downstream integrations already depend on a stable type.
    """


class NotFound(ConfigError):
    """Indicates an optional configuration source was not discovered.

    Used when files, directory entries, or environment variable namespaces are
    genuinely missing; callers generally treat this as informational rather than
    fatal.
    """
