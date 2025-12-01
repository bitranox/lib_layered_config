"""Shared helpers for normalising user-provided platform aliases.

Bridge CLI/example inputs with resolver internals by translating human-friendly
platform strings into the canonical identifiers expected across adapters and
documentation.

Contents:
    - ``normalise_resolver_platform``: map CLI adapter aliases to ``sys.platform``
      style identifiers.
    - ``normalise_examples_platform``: map example-generation aliases to the two
      supported documentation families.
    - ``_sanitize`` plus canonical mapping constants that keep user inputs tidy and
      predictable.

System Role:
    Reusable utilities consumed by CLI commands and example tooling to ensure
    terminology matches ``docs/systemdesign/concept.md`` regardless of user input
    quirks.
"""

from __future__ import annotations

from typing import Final

#: Canonical resolver identifiers used when wiring the path resolver adapter.
#: Values mirror ``sys.platform`` strings so downstream code can branch safely.
_CANONICAL_RESOLVER: Final[dict[str, str]] = {
    "linux": "linux",
    "posix": "linux",
    "darwin": "darwin",
    "mac": "darwin",
    "macos": "darwin",
    "windows": "win32",
    "win": "win32",
    "win32": "win32",
    "wine": "win32",
}

#: Canonical families used by documentation/example helpers. They collapse the
#: wide variety of aliases into the two supported directory layouts.
_CANONICAL_EXAMPLES: Final[dict[str, str]] = {
    "posix": "posix",
    "linux": "posix",
    "darwin": "posix",
    "mac": "posix",
    "macos": "posix",
    "windows": "windows",
    "win": "windows",
    "win32": "windows",
    "wine": "windows",
}


def _sanitize(alias: str | None) -> str | None:
    """Return a lower-cased alias stripped of whitespace when *alias* is truthy.

    User input may include spacing or mixed casing; sanitising up front keeps the
    canonical lookup tables compact and dependable.

    Args:
        alias: Optional raw alias provided by a user or CLI flag. ``None`` indicates no
            override.

    Returns:
        Lower-case alias when *alias* contains characters, otherwise ``None`` when
        no override is requested.

    Raises:
        ValueError: If *alias* contains only whitespace, because such inputs indicate a user
            error that should surface immediately.

    Examples:
        >>> _sanitize('  MacOS  ')
        'macos'
        >>> _sanitize(None) is None
        True
        >>> _sanitize('   ')
        Traceback (most recent call last):
        ...
        ValueError: Platform alias cannot be empty.
    """
    if alias is None:
        return None
    stripped = alias.strip().lower()
    if not stripped:
        raise ValueError("Platform alias cannot be empty.")
    return stripped


def normalise_resolver_platform(alias: str | None) -> str | None:
    """Return canonical resolver platform identifiers for *alias*.

    The path resolver adapter expects ``sys.platform`` style identifiers. This
    helper converts human-friendly values (``"mac"``, ``"win"``) into the canonical
    tokens documented in the system design.

    Args:
        alias: User-provided alias or ``None``. ``None`` preserves auto-detection.

    Returns:
        Canonical resolver identifier or ``None`` when auto-detection should be
        used.

    Raises:
        ValueError: If *alias* is not recognised. The error message enumerates valid options
            so CLI tooling can surface helpful guidance.

    Examples:
        >>> normalise_resolver_platform('mac')
        'darwin'
        >>> normalise_resolver_platform('win32')
        'win32'
        >>> normalise_resolver_platform(None) is None
        True
        >>> normalise_resolver_platform('beos')
        Traceback (most recent call last):
        ...
        ValueError: Platform must be one of: darwin, linux, mac, macos, posix, win, win32, windows, wine.
    """
    sanitized = _sanitize(alias)
    if sanitized is None:
        return None
    try:
        return _CANONICAL_RESOLVER[sanitized]
    except KeyError as exc:  # pragma: no cover - exercised via caller tests
        allowed = ", ".join(sorted(_CANONICAL_RESOLVER))
        raise ValueError(f"Platform must be one of: {allowed}.") from exc


def normalise_examples_platform(alias: str | None) -> str | None:
    """Return the example-generation platform family for *alias*.

    Documentation and example helpers target two directory layouts (POSIX and
    Windows). This function collapses a wide variety of synonyms into those
    families for predictable template generation.

    Args:
        alias: User-provided alias or ``None`` to let the caller choose a default.

    Returns:
        Canonical example platform (``"posix"`` or ``"windows"``) or ``None`` when
        the caller should rely on runtime defaults.

    Raises:
        ValueError: If *alias* is provided but not known.

    Examples:
        >>> normalise_examples_platform('darwin')
        'posix'
        >>> normalise_examples_platform('windows')
        'windows'
        >>> normalise_examples_platform(None) is None
        True
        >>> normalise_examples_platform('amiga')
        Traceback (most recent call last):
        ...
        ValueError: Platform must be one of: darwin, linux, mac, macos, posix, win, win32, windows, wine.
    """
    sanitized = _sanitize(alias)
    if sanitized is None:
        return None
    try:
        return _CANONICAL_EXAMPLES[sanitized]
    except KeyError as exc:  # pragma: no cover - exercised via caller tests
        allowed = ", ".join(sorted(_CANONICAL_EXAMPLES))
        raise ValueError(f"Platform must be one of: {allowed}.") from exc
