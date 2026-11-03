"""Domain error taxonomy shared across layers.

Codifies the error classes referenced throughout ``docs/systemdesign`` so the
application and adapter layers can communicate failures without depending on
concrete implementations.

Contents:
    - ``ConfigError``: base class for every library-specific exception.
    - ``InvalidFormatError``: raised when structured configuration cannot be parsed.
    - ``ValidationError``: an identifier, platform or deploy argument was refused.
    - ``DeployDestinationError``: a deploy destination is a symbolic link or not a regular file.
    - ``NotFoundError``: indicates optional configuration sources were absent.

System Role:
    Adapters raise these exceptions; the composition root and CLI translate them
    into operator-facing messages without leaking implementation details.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "DeployDestinationError",
    "InvalidFormatError",
    "NotFoundError",
    "ValidationError",
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


class DeployDestinationError(ValidationError):
    """Raised when a file deploy would write is a symbolic link (dangling or not) or not a regular file.

    Deploy neither writes through a link (which would change the file it points at) nor replaces
    it, and it writes only regular files (reading a FIFO there would block), so every such
    destination is refused, one line each, before anything is written. A
    :class:`ValidationError`, so ``except ValidationError`` still catches every deploy refusal.
    """


class NotFoundError(ConfigError):
    """Indicates an optional configuration source was not discovered.

    Used when files, directory entries, or environment variable namespaces are
    genuinely missing; callers generally treat this as informational rather than
    fatal.
    """
