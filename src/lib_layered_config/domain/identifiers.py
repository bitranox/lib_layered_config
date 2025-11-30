"""Identifier validation and layer enumeration.

Purpose
-------
Provide safe identifier handling and layer name constants used throughout the
library, preventing path traversal attacks and magic string usage.

Contents
--------
- ``Layer``: enumeration of configuration layer names.
- ``validate_identifier``: ensure identifiers are safe for filesystem paths.
- ``validate_hostname``: ensure hostname is safe for filesystem paths.
"""

from __future__ import annotations

from enum import Enum


class Layer(str, Enum):
    """Configuration layer names in precedence order.

    Why
    ----
    Replace magic strings with type-safe enumeration, enabling IDE completion
    and preventing typos in layer name references.

    Values
    ------
    DEFAULTS
        Lowest precedence - bundled application defaults.
    APP
        System-wide application configuration.
    HOST
        Machine-specific overrides.
    USER
        Per-user preferences.
    DOTENV
        Project-local `.env` file values.
    ENV
        Environment variable overrides (highest precedence).
    """

    DEFAULTS = "defaults"
    APP = "app"
    HOST = "host"
    USER = "user"
    DOTENV = "dotenv"
    ENV = "env"


def validate_identifier(value: str, name: str) -> str:
    """Ensure identifier contains no path separators or parent directory references.

    Why
    ----
    Prevent path traversal attacks when identifiers are used in filesystem paths.

    Parameters
    ----------
    value:
        The identifier value to validate.
    name:
        Parameter name for error messages (e.g., "vendor", "app", "slug").

    Returns
    -------
    str
        The validated identifier (unchanged if valid).

    Raises
    ------
    ValueError
        When the identifier contains invalid characters.

    Examples
    --------
    >>> validate_identifier("myapp", "slug")
    'myapp'
    >>> validate_identifier("my-app_v2", "slug")
    'my-app_v2'
    >>> validate_identifier("../etc", "vendor")
    Traceback (most recent call last):
        ...
    ValueError: vendor contains invalid path characters: ../etc
    """
    if "/" in value or "\\" in value:
        raise ValueError(f"{name} contains invalid path characters: {value}")
    if value.startswith("."):
        raise ValueError(f"{name} cannot start with a dot: {value}")
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def validate_hostname(value: str) -> str:
    """Ensure hostname is safe for use in filesystem paths.

    Why
    ----
    Hostnames are used to construct file paths like ``hosts/{hostname}.toml``.
    While hostnames from ``socket.gethostname()`` are typically safe, defensive
    validation prevents edge cases.

    Parameters
    ----------
    value:
        The hostname to validate.

    Returns
    -------
    str
        The validated hostname (unchanged if valid).

    Raises
    ------
    ValueError
        When the hostname contains path separators.

    Examples
    --------
    >>> validate_hostname("web-server-01")
    'web-server-01'
    >>> validate_hostname("server.local")
    'server.local'
    >>> validate_hostname("../etc")
    Traceback (most recent call last):
        ...
    ValueError: hostname contains invalid path characters: ../etc
    """
    if "/" in value or "\\" in value:
        raise ValueError(f"hostname contains invalid path characters: {value}")
    return value


__all__ = ["Layer", "validate_identifier", "validate_hostname"]
