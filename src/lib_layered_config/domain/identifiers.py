"""Identifier validation and layer enumeration.

Provide safe identifier handling and layer name constants used throughout the
library, preventing path traversal attacks and ensuring cross-platform filesystem
compatibility.

Contents:
    - ``Layer``: enumeration of configuration layer names.
    - ``validate_path_segment``: core validation for filesystem path segments (strict, no spaces).
    - ``validate_identifier``: validate slug/profile identifiers (strict, no spaces).
    - ``validate_vendor_app``: validate vendor/app names (permissive, allows spaces).
    - ``validate_profile``: validate optional profile names (strict, no spaces).
    - ``validate_hostname``: validate hostname for filesystem paths (allows dots for FQDN).

Validation Strategy:
    - **vendor/app**: Use ``validate_vendor_app()`` - allows spaces for macOS/Windows paths
      (e.g., ``/Library/Application Support/Acme Corp/My App/``).
    - **slug/profile**: Use ``validate_identifier()`` - strict, no spaces allowed
      (used in Linux paths and environment variable prefixes).
    - **hostname**: Use ``validate_hostname()`` - allows dots for FQDNs.
"""

from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache

# Windows reserved device names (case-insensitive)
_WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)

# Characters invalid in filenames on Windows and/or problematic on Linux
# < > : " | ? * / \ and null byte
_INVALID_CHARS_PATTERN: re.Pattern[str] = re.compile(r'[<>:"|?*\\/\x00]')

# Valid strict identifier pattern: ASCII alphanumeric, hyphen, underscore, dot (not at start)
# Used for: slug, profile
_VALID_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

# Valid permissive identifier pattern: ASCII alphanumeric, hyphen, underscore, dot, space
# Used for: vendor, app (which can have spaces on macOS/Windows paths)
_VALID_PERMISSIVE_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\- ]*$")

# Valid hostname pattern: ASCII alphanumeric, hyphen, dot (FQDN support)
# Hostnames can start with alphanumeric, contain hyphens and dots
_VALID_HOSTNAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*$")


# ============================================================================
# Validation Helper Functions (reduce cyclomatic complexity)
# ============================================================================


def _check_not_empty(value: str, name: str) -> None:
    """Raise ValueError if value is empty."""
    if not value:
        raise ValueError(f"{name} cannot be empty")


def _check_ascii_only(value: str, name: str) -> None:
    """Raise ValueError if value contains non-ASCII characters."""
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(f"{name} contains non-ASCII characters: {value}") from None


def _check_no_invalid_chars(value: str, name: str) -> None:
    """Raise ValueError if value contains filesystem-invalid characters."""
    if _INVALID_CHARS_PATTERN.search(value):
        raise ValueError(f"{name} contains invalid characters: {value}")


def _check_not_windows_reserved(value: str, name: str, *, split_on_space: bool = False) -> None:
    """Raise ValueError if value is a Windows reserved name."""
    # Extract base name (before first dot, optionally before first space)
    base_name = value.split(".")[0]
    if split_on_space:
        base_name = base_name.split()[0]
    if base_name.upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{name} is a Windows reserved name: {value}")


def _check_no_trailing_dot_or_space(value: str, name: str) -> None:
    """Raise ValueError if value ends with dot or space (Windows restriction)."""
    if value.endswith(".") or value.endswith(" "):
        raise ValueError(f"{name} cannot end with a dot or space: {value}")


def _raise_pattern_error(value: str, name: str, *, check_space_start: bool) -> None:
    """Raise appropriate ValueError for pattern mismatch.

    Args:
        value: The value that failed validation.
        name: Parameter name for error messages.
        check_space_start: If True, space is checked as an invalid start character.
    """
    if value.startswith("."):
        raise ValueError(f"{name} cannot start with a dot: {value}")
    invalid_starts = ("-", "_", " ") if check_space_start else ("-", "_")
    if any(value.startswith(c) for c in invalid_starts):
        raise ValueError(f"{name} must start with an alphanumeric character: {value}")
    raise ValueError(f"{name} contains invalid characters: {value}")


def _check_permissive_pattern(value: str, name: str) -> None:
    """Check value matches permissive pattern (allows spaces for vendor/app)."""
    if _VALID_PERMISSIVE_PATTERN.match(value):
        return
    _raise_pattern_error(value, name, check_space_start=True)


def _check_hostname_pattern(value: str, name: str) -> None:
    """Check value matches hostname pattern (alphanumeric, hyphen, dot)."""
    if _VALID_HOSTNAME_PATTERN.match(value):
        return
    if value.startswith(".") or value.startswith("-"):
        raise ValueError(f"{name} must start with an alphanumeric character: {value}")
    raise ValueError(f"{name} contains invalid characters: {value}")


def _check_no_trailing_space(value: str, name: str) -> None:
    """Raise ValueError if value ends with space."""
    if value.endswith(" "):
        raise ValueError(f"{name} cannot end with a space: {value}")


class Layer(str, Enum):
    """Configuration layer names in precedence order.

    Replace magic strings with type-safe enumeration, enabling IDE completion
    and preventing typos in layer name references.

    Attributes:
        DEFAULTS: Lowest precedence - bundled application defaults.
        APP: System-wide application configuration.
        HOST: Machine-specific overrides.
        USER: Per-user preferences.
        DOTENV: Project-local `.env` file values.
        ENV: Environment variable overrides (highest precedence).
    """

    DEFAULTS = "defaults"
    APP = "app"
    HOST = "host"
    USER = "user"
    DOTENV = "dotenv"
    ENV = "env"


def validate_path_segment(value: str, name: str, *, allow_dots: bool = False) -> str:
    """Validate a string for safe use as a filesystem path segment.

    Ensures identifiers (vendor, app, slug, profile) are safe on Windows and Linux,
    preventing path traversal attacks and encoding issues.

    Args:
        value: The string to validate.
        name: Parameter name for error messages (e.g., "vendor", "slug").
        allow_dots: If True, allow dots within the value (for hostnames).

    Returns:
        The validated string (unchanged if valid).

    Raises:
        ValueError: When the value fails validation (empty, non-ASCII, invalid chars,
            path separators, Windows reserved names, or trailing dot/space).

    Examples:
        >>> validate_path_segment("myapp", "slug")
        'myapp'
        >>> validate_path_segment("Acme", "vendor")
        'Acme'
    """
    _check_not_empty(value, name)
    _check_ascii_only(value, name)
    _check_no_invalid_chars(value, name)
    _check_strict_pattern(value, name, allow_dots)
    _check_not_windows_reserved(value, name)
    _check_no_trailing_dot_or_space(value, name)
    return value


def _check_strict_pattern(value: str, name: str, allow_dots: bool) -> None:
    """Check value matches strict identifier pattern (no spaces)."""
    if allow_dots:
        return
    if _VALID_IDENTIFIER_PATTERN.match(value):
        return
    _raise_pattern_error(value, name, check_space_start=False)


@lru_cache(maxsize=64)
def validate_identifier(value: str, name: str) -> str:
    """Validate a strict identifier (slug, profile) for filesystem safety.

    Prevent path traversal attacks and ensure cross-platform filesystem compatibility
    when identifiers are used to construct directory paths.

    Note:
        This is for strict identifiers (slug, profile) that should not contain spaces.
        For vendor/app which allow spaces, use ``validate_vendor_app()``.
        Results are cached for performance when validating the same identifiers repeatedly.

    Args:
        value: The identifier value to validate.
        name: Parameter name for error messages (e.g., "slug", "profile").

    Returns:
        The validated identifier (unchanged if valid).

    Raises:
        ValueError: When the identifier contains invalid characters or patterns.

    Examples:
        >>> validate_identifier("myapp", "slug")
        'myapp'
        >>> validate_identifier("my-app_v2", "slug")
        'my-app_v2'
        >>> validate_identifier("../etc", "slug")
        Traceback (most recent call last):
            ...
        ValueError: slug contains invalid characters: ../etc
    """
    return validate_path_segment(value, name, allow_dots=False)


@lru_cache(maxsize=64)
def validate_vendor_app(value: str, name: str) -> str:
    """Validate vendor or app identifier for filesystem safety (allows spaces).

    Vendor and app names are used in macOS and Windows paths which support spaces
    (e.g., ``/Library/Application Support/Acme Corp/My App/``).
    This function allows spaces while still preventing path traversal attacks.
    Results are cached for performance when validating the same values repeatedly.

    Args:
        value: The vendor or app value to validate.
        name: Parameter name for error messages ("vendor" or "app").

    Returns:
        The validated value (unchanged if valid).

    Raises:
        ValueError: When the value contains invalid characters or patterns.

    Examples:
        >>> validate_vendor_app("Acme Corp", "vendor")
        'Acme Corp'
        >>> validate_vendor_app("My App", "app")
        'My App'
        >>> validate_vendor_app("Btx Fix Mcp", "app")
        'Btx Fix Mcp'
        >>> validate_vendor_app("../etc", "vendor")
        Traceback (most recent call last):
            ...
        ValueError: vendor contains invalid characters: ../etc
    """
    _check_not_empty(value, name)
    _check_ascii_only(value, name)
    _check_no_invalid_chars(value, name)
    _check_permissive_pattern(value, name)
    _check_not_windows_reserved(value, name, split_on_space=True)
    _check_no_trailing_dot_or_space(value, name)
    return value


def validate_profile(value: str | None) -> str | None:
    """Validate profile name or return None if not provided.

    Profile names become path segments, so they must be validated against
    path traversal attacks and ensured cross-platform filesystem compatibility.

    Args:
        value: The profile name to validate, or None for no profile.

    Returns:
        The validated profile name, or None if no profile.

    Raises:
        ValueError: When the profile name contains invalid characters.

    Examples:
        >>> validate_profile(None) is None
        True
        >>> validate_profile("test")
        'test'
        >>> validate_profile("prod-v1")
        'prod-v1'
        >>> validate_profile("../etc")
        Traceback (most recent call last):
            ...
        ValueError: profile contains invalid characters: ../etc
    """
    if value is None:
        return None
    return validate_identifier(value, "profile")


@lru_cache(maxsize=16)
def validate_hostname(value: str) -> str:
    """Ensure hostname is safe for use in filesystem paths.

    Hostnames are used to construct file paths like ``hosts/{hostname}.toml``.
    While hostnames from ``socket.gethostname()`` are typically safe, defensive
    validation prevents path traversal and ensures cross-platform safety.
    Results are cached for performance since hostname rarely changes.

    Validation Rules:
        1. Must not be empty
        2. Must contain only ASCII characters
        3. Must start with alphanumeric character
        4. May contain alphanumeric, hyphen, and dot (for FQDNs)
        5. Must not contain path separators or Windows-invalid characters
        6. Must not be a Windows reserved name

    Args:
        value: The hostname to validate.

    Returns:
        The validated hostname (unchanged if valid).

    Raises:
        ValueError: When the hostname fails validation.

    Examples:
        >>> validate_hostname("web-server-01")
        'web-server-01'
        >>> validate_hostname("server.local")
        'server.local'
        >>> validate_hostname("../etc")
        Traceback (most recent call last):
            ...
        ValueError: hostname contains invalid characters: ../etc
        >>> validate_hostname("café")
        Traceback (most recent call last):
            ...
        ValueError: hostname contains non-ASCII characters: café
    """
    _check_not_empty(value, "hostname")
    _check_ascii_only(value, "hostname")
    _check_no_invalid_chars(value, "hostname")
    _check_hostname_pattern(value, "hostname")
    _check_not_windows_reserved(value, "hostname")
    _check_no_trailing_space(value, "hostname")
    return value


__all__ = [
    "Layer",
    "validate_path_segment",
    "validate_identifier",
    "validate_vendor_app",
    "validate_profile",
    "validate_hostname",
]
