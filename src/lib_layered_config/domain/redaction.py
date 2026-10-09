"""Pure domain logic for masking sensitive configuration values.

Provide a recursive redaction mechanism that replaces values associated with
sensitive key names (passwords, tokens, secrets, API keys) with a placeholder
string.  This prevents accidental exposure of secrets in logs, CLI output,
debug dumps, or JSON exports.

Contents:
    - ``REDACTED_PLACEHOLDER``: constant string used as the replacement value.
    - ``is_sensitive``: predicate testing whether a key name matches known
      sensitive patterns.
    - ``NotSensitiveKeys``: dotted paths an application declares as not secret.
    - ``is_sensitive_at``: predicate combining the name rule with those declarations.
    - ``redact_mapping``: recursive function that creates a redacted copy of a
      configuration mapping.

System Role:
    Called by ``Config.to_json(redact=True)`` and ``Config.as_dict(redact=True)``
    to produce safe representations of configuration data.  Lives in the domain
    layer with no external dependencies (stdlib only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast

from .errors import InvalidFormatError

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

__all__ = ["REDACTED_PLACEHOLDER", "NotSensitiveKeys", "is_sensitive", "is_sensitive_at", "redact_mapping"]

#: Maximum nesting depth for redaction. Guards against an opaque ``RecursionError`` on a
#: pathologically deep mapping passed to the public ``redact_mapping``.
_MAX_REDACT_DEPTH: Final[int] = 100

REDACTED_PLACEHOLDER: Final[str] = "***REDACTED***"
"""Constant replacing sensitive values in redacted output."""

#: Separates the segments of a declared path, as in ``Config.get("db.host")``.
_PATH_DELIMITER: Final[str] = "."

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


@dataclass(frozen=True, slots=True)
class NotSensitiveKeys:
    """Dotted key paths an application declares as not secret although their name looks like one.

    ``is_sensitive`` decides by name, so a size such as ``max_token_bytes`` is masked like a
    token. An application that knows its own schema lists such keys here; every other key keeps
    the name rule. Paths match case-insensitively, and an item inside a list is addressed by the
    list's own path, with no index. A declaration covers its own path only: keys below it are
    still checked one by one, and a masked ancestor stays masked as a whole.

    Build one with :meth:`of`, the documented constructor that validates and lowercases;
    constructing it directly is checked too and refuses anything :meth:`of` would not produce.

    Attributes:
        paths: The declared paths, lowercased, one tuple of segments each.

    Examples:
        >>> keys = NotSensitiveKeys.of(["performance.max_token_bytes"])
        >>> keys.covers(("Performance", "MAX_TOKEN_BYTES")), keys.covers(("performance",))
        (True, False)
        >>> list(keys)
        ['performance.max_token_bytes']
    """

    paths: frozenset[tuple[str, ...]]

    NONE: ClassVar[NotSensitiveKeys]

    def __post_init__(self) -> None:
        """Refuse paths that :meth:`of` would never build, so a direct construction cannot mis-mask.

        Raises:
            TypeError: ``paths`` is not a frozenset of tuples of ``str``.
            ValueError: A segment is empty or not lowercase.

        Examples:
            >>> NotSensitiveKeys(frozenset({("A", "b")}))
            Traceback (most recent call last):
            ...
            ValueError: not-sensitive path ('A', 'b') needs lowercase, non-empty segments: use NotSensitiveKeys.of
        """
        if not isinstance(cast("object", self.paths), frozenset):
            raise TypeError(f"paths must be a frozenset of tuples of str, got {type(self.paths).__name__}")
        for path in self.paths:
            _check_built_path(path)

    @classmethod
    def of(cls, declared: Iterable[str] | None) -> NotSensitiveKeys:
        """Return the declaration for *declared*, validated once at the boundary.

        Args:
            declared: Dotted paths, an existing instance (returned as is), or ``None`` for none.

        Returns:
            The declaration.

        Raises:
            TypeError: *declared* is a single ``str`` (iterating it would declare its characters),
                or an entry is not a ``str``.
            ValueError: An entry is empty or has an empty segment (``"a..b"``).

        Examples:
            >>> NotSensitiveKeys.of(None) is NotSensitiveKeys.NONE
            True
            >>> NotSensitiveKeys.of("a.b")
            Traceback (most recent call last):
            ...
            TypeError: not_sensitive takes an iterable of dotted paths, not a single str: write ['a.b']
        """
        if declared is None:
            return cls.NONE
        if isinstance(declared, NotSensitiveKeys):
            return declared
        if isinstance(declared, str):
            raise TypeError(f"not_sensitive takes an iterable of dotted paths, not a single str: write [{declared!r}]")
        return cls(frozenset(_declared_path(entry) for entry in declared))

    def covers(self, path: Sequence[str]) -> bool:
        """Return whether *path* (segments, any case) was declared.

        Raises:
            TypeError: *path* is a ``str``, which would be read as a sequence of characters.

        Examples:
            >>> NotSensitiveKeys.of(["a.b"]).covers(["A", "b"]), NotSensitiveKeys.NONE.covers(["a", "b"])
            (True, False)
            >>> NotSensitiveKeys.of(["a.b"]).covers("a.b")
            Traceback (most recent call last):
            ...
            TypeError: path is a sequence of segments, not a dotted str: write tuple('a.b'.split('.'))
        """
        _refuse_str_path(path)
        return tuple(segment.lower() for segment in path) in self.paths

    def __iter__(self) -> Iterator[str]:
        """Yield the declared paths as dotted strings, sorted, so an instance is itself an ``Iterable[str]``."""
        return iter(sorted(_PATH_DELIMITER.join(path) for path in self.paths))


NotSensitiveKeys.NONE = NotSensitiveKeys(frozenset())


def _check_built_path(path: object) -> None:
    """Refuse *path* unless it is a tuple of lowercase, non-empty ``str`` segments.

    Examples:
        >>> _check_built_path(("a", "b"))
    """
    if not isinstance(path, tuple) or not all(isinstance(segment, str) for segment in cast("tuple[object, ...]", path)):
        raise TypeError(f"each not-sensitive path must be a tuple of str, got {path!r}")
    segments = cast("tuple[str, ...]", path)
    if not segments or not all(segments) or any(segment != segment.lower() for segment in segments):
        raise ValueError(
            f"not-sensitive path {segments!r} needs lowercase, non-empty segments: use NotSensitiveKeys.of"
        )


def _refuse_str_path(path: object) -> None:
    """Raise ``TypeError`` for a ``str`` path: its characters would be read as the segments.

    Examples:
        >>> _refuse_str_path(("a", "b"))
        >>> _refuse_str_path("a.b")
        Traceback (most recent call last):
        ...
        TypeError: path is a sequence of segments, not a dotted str: write tuple('a.b'.split('.'))
    """
    if isinstance(path, str):
        raise TypeError(f"path is a sequence of segments, not a dotted str: write tuple({path!r}.split('.'))")


def _declared_path(entry: object) -> tuple[str, ...]:
    """Return *entry* as lowercased segments, refusing a non-str entry or an empty segment.

    Examples:
        >>> _declared_path("Performance.Max_Token_Bytes")
        ('performance', 'max_token_bytes')
    """
    if not isinstance(entry, str):
        raise TypeError(f"not_sensitive entries must be str, got {type(entry).__name__}")
    segments = tuple(segment.lower() for segment in entry.split(_PATH_DELIMITER))
    if not all(segments):
        raise ValueError(f"not_sensitive entry {entry!r} has an empty segment")
    return segments


def is_sensitive_at(path: Sequence[str], *, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE) -> bool:
    """Return whether the key at *path* is masked: its own name looks secret and nothing declared it.

    Args:
        path: The key's segments from the root, its own name last.
        not_sensitive: Paths the application declared not sensitive.

    Returns:
        Whether the value at *path* must be treated as a secret.

    Raises:
        TypeError: *path* is a ``str``; a dotted name is not a path, split it first.

    Examples:
        >>> declared = NotSensitiveKeys.of(["performance.max_token_bytes"])
        >>> is_sensitive_at(("performance", "max_token_bytes"), not_sensitive=declared)
        False
        >>> is_sensitive_at(("db", "password"), not_sensitive=declared)
        True
        >>> is_sensitive_at("db.password")
        Traceback (most recent call last):
        ...
        TypeError: path is a sequence of segments, not a dotted str: write tuple('db.password'.split('.'))
    """
    _refuse_str_path(path)
    return bool(path) and is_sensitive(path[-1]) and not not_sensitive.covers(path)


def redact_mapping(data: dict[str, Any], *, not_sensitive: Iterable[str] | None = None) -> dict[str, Any]:
    """Return a deep copy of *data* with sensitive values replaced.

    Creates a new dictionary without mutating the input.  Recurses into nested
    dictionaries and lists of dictionaries to redact sensitive keys at any
    depth.

    Args:
        data: Configuration mapping to redact.
        not_sensitive: Dotted paths declared not sensitive although their name looks it
            (see :class:`NotSensitiveKeys`); they are left as they are.

    Returns:
        New mapping with sensitive values replaced by ``REDACTED_PLACEHOLDER``.

    Raises:
        InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
        TypeError: *not_sensitive* is a single ``str`` or holds a non-``str`` entry.
        ValueError: A *not_sensitive* entry has an empty segment.

    Examples:
        >>> redact_mapping({"password": "s3cret", "host": "localhost"})
        {'password': '***REDACTED***', 'host': 'localhost'}
        >>> original = {"db": {"password": "s3cret"}}
        >>> redact_mapping(original)
        {'db': {'password': '***REDACTED***'}}
        >>> original["db"]["password"]
        's3cret'
        >>> redact_mapping({"max_token_bytes": 4096}, not_sensitive=["max_token_bytes"])
        {'max_token_bytes': 4096}
    """
    return _Redactor(NotSensitiveKeys.of(not_sensitive)).mapping(data, path=(), depth=0)


@dataclass(frozen=True, slots=True)
class _Redactor:
    """One redaction walk, carrying the declared exemptions to every depth."""

    not_sensitive: NotSensitiveKeys

    def mapping(self, mapping: dict[str, Any], *, path: tuple[str, ...], depth: int) -> dict[str, Any]:
        """Return *mapping* (found at *path*) with each sensitive key's value replaced.

        Raises:
            InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
        """
        _ensure_depth(depth)
        result: dict[str, Any] = {}
        for key, value in mapping.items():
            key_path = (*path, key)
            if is_sensitive_at(key_path, not_sensitive=self.not_sensitive):
                result[key] = REDACTED_PLACEHOLDER
            elif isinstance(value, dict):
                result[key] = self.mapping(cast("dict[str, Any]", value), path=key_path, depth=depth + 1)
            elif isinstance(value, list):
                result[key] = self.items(cast("list[Any]", value), path=key_path, depth=depth + 1)
            else:
                result[key] = value
        return result

    def items(self, items: list[Any], *, path: tuple[str, ...], depth: int) -> list[Any]:
        """Return *items* (the list at *path*) with its dictionaries redacted; other items pass through.

        A dictionary inside the list keeps the list's *path*: a declaration addresses list items
        without an index.

        Raises:
            InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
        """
        _ensure_depth(depth)
        return [
            self.mapping(cast("dict[str, Any]", item), path=path, depth=depth + 1) if isinstance(item, dict) else item
            for item in items
        ]


def _ensure_depth(depth: int) -> None:
    """Refuse a walk deeper than :data:`_MAX_REDACT_DEPTH` with a readable error, not RecursionError."""
    if depth > _MAX_REDACT_DEPTH:
        raise InvalidFormatError(f"Configuration nesting exceeds the maximum depth of {_MAX_REDACT_DEPTH}")
