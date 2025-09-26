"""Plainspoken exception hierarchy for configuration failures.

Purpose
    Offer a single, memorable taxonomy that adapters and applications can share
    when reporting configuration issues. The hierarchy sits in the domain layer
    so every outer component can depend on it without creating import cycles.

Contents
    - ``ConfigError``: root for every library-specific exception.
    - ``InvalidFormat``: wrap syntax/parse failures.
    - ``ValidationError``: reserve semantic validation failures.
    - ``NotFound``: signal missing-yet-optional resources.

System Integration
    Adapters raise the specialised subclasses; callers often catch
    :class:`ConfigError` to treat all library failures uniformly. The
    composition root may wrap adapter-specific exceptions into
    :class:`ConfigError` derivatives to keep external contracts stable.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "InvalidFormat",
    "ValidationError",
    "NotFound",
]


class ConfigError(Exception):
    """Root of the library's configuration error tree.

    Why
        Gives consumers a single ``except ConfigError`` hook when they do not
        care about fine-grained failure modes.
    When
        Raised directly only in guard rails; most modules raise subclasses.
    """


class InvalidFormat(ConfigError):
    """Wrap syntactic parsing failures.

    Why
        Communicates that a configuration source exists but could not be parsed
        into structured data.
    When
        Raised by file loaders, dotenv parsing, or other structured parsers.
    """


class ValidationError(ConfigError):
    """Reserved for semantic validation errors.

    Why
        Keeps room for future schema validation without breaking the hierarchy.
    When
        Raised once semantic validation is introduced; currently unused on
        purpose.
    """


class NotFound(ConfigError):
    """Signal optional artifacts that could not be located.

    Why
        Allows adapters to note missing files or directories without treating
        the situation as fatal.
    When
        Raised by path resolvers and loaders when an optional resource is
        absent.
    """
