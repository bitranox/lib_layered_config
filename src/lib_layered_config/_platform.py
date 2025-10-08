"""Shared helpers for normalising user-provided platform aliases."""

from __future__ import annotations

from typing import Final

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
    if alias is None:
        return None
    stripped = alias.strip().lower()
    if not stripped:
        raise ValueError("Platform alias cannot be empty.")
    return stripped


def normalise_resolver_platform(alias: str | None) -> str | None:
    """Return canonical resolver platform identifiers for *alias*.

    ``None`` is returned unchanged so callers can fall back to runtime
    detection. When an alias is provided but unknown, ``ValueError`` is
    raised with a descriptive message suitable for surfacing to CLI users.
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

    Returns ``None`` when *alias* is ``None`` so callers can defer to their
    own defaults. Unknown aliases raise ``ValueError`` mirroring the resolver
    helper.
    """

    sanitized = _sanitize(alias)
    if sanitized is None:
        return None
    try:
        return _CANONICAL_EXAMPLES[sanitized]
    except KeyError as exc:  # pragma: no cover - exercised via caller tests
        allowed = ", ".join(sorted(_CANONICAL_EXAMPLES))
        raise ValueError(f"Platform must be one of: {allowed}.") from exc
