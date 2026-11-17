"""Pure domain logic for masking sensitive configuration values.

Provide a recursive redaction mechanism that replaces values associated with
sensitive key names (passwords, tokens, secrets, API keys) with a placeholder
string, and masks the password of every URL in a string value under any key.
This prevents accidental exposure of secrets in logs, CLI output,
debug dumps, or JSON exports.

Contents:
    - ``REDACTED_PLACEHOLDER``: constant string used as the replacement value.
    - ``is_sensitive``: predicate testing whether a key name matches known
      sensitive patterns.
    - ``NotSensitiveKeys``: dotted paths an application declares as not secret.
    - ``is_sensitive_at``: predicate combining the name rule with those declarations.
    - ``redact_value_at``: the value at one dotted path as the redacted view shows it.
    - ``redact_mapping``: recursive function that creates a redacted copy of a
      configuration mapping.

System Role:
    Called by ``Config.to_json(redact=True)`` and ``Config.as_dict(redact=True)``
    to produce safe representations of configuration data.  Lives in the domain
    layer with no external dependencies (stdlib only).
"""

from __future__ import annotations

import re
import string
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast

from .errors import InvalidFormatError

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

__all__ = [
    "REDACTED_PLACEHOLDER",
    "NotSensitiveKeys",
    "is_sensitive",
    "is_sensitive_at",
    "redact_mapping",
    "redact_value_at",
]

#: Maximum nesting depth for redaction, counting every mapping, list and tuple level. Guards
#: against an opaque ``RecursionError`` on a pathological document. It sits well above the 100
#: MAPPING levels the merge accepts plus any list nesting a real configuration has, so a redacted
#: view never refuses what reading accepted, and well below the interpreter's recursion limit
#: (each level costs two frames).
_MAX_REDACT_DEPTH: Final[int] = 300

REDACTED_PLACEHOLDER: Final[str] = "***REDACTED***"
"""Constant replacing sensitive values in redacted output."""

#: Separates the segments of a declared path, as in ``Config.get("db.host")``.
_PATH_DELIMITER: Final[str] = "."

_SENSITIVE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|_)(?:"
    r"password|passwd|passphrase|pwd|pass|secret|token|credential|apikey|privatekey|privkey|bearer|cookie|jwt"
    r"|signature|session_id|sessionid|authorization"
    r")s?\d*(?:_|$)"
    # `_key` requires a leading underscore so compound names (api_key, access_key,
    # aws_access_key_id, signing_key) match while a field literally named "key" - a
    # common non-secret map/identifier field - does not get swept up. More letters may follow it
    # (keyset, keysecret: key material) and so may digits, here and after every stem above
    # (password2, api_key1), as numbered secrets are commonly named.
    r"|_key(?:s|\d*(?:_|$))",
    re.IGNORECASE,
)

#: Where a camelCase or PascalCase name changes words: ``dbPassword`` -> ``db|Password`` and
#: ``DBPassword`` -> ``DB|Password``. The pattern above knows only the underscore as a word
#: boundary, so these and the kebab-case separators are rewritten to one before it runs.
_CAMEL_BOUNDARY: re.Pattern[str] = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS: re.Pattern[str] = re.compile(r"[-\s.]+")

#: What closes a URL's scheme; each one in a value is where :func:`_url_starts` looks for a URL.
_SCHEME_END: Final[str] = "://"

#: Characters of a scheme after its first letter (RFC 3986, 3.1), plus the ``:`` between sub-schemes
#: (``jdbc:mysql``): the run :func:`_scheme_start` walks back over.
_SCHEME_RUN: Final[frozenset[str]] = frozenset(string.ascii_letters + string.digits + "+.-:")

#: Where a URL's authority ends when nothing in it is unescaped.
_AUTHORITY_END = "/?#"


def is_sensitive(key: str) -> bool:
    """Return ``True`` when *key* matches a known sensitive name pattern.

    Patterns are matched case-insensitively at word boundaries. Supported stems include
    ``password``, ``passwd``, ``passphrase``, ``pwd``, ``pass``, ``secret``, ``token``, ``credential``,
    ``apikey``, ``privatekey``, ``privkey``, ``bearer``, ``cookie``, ``jwt``, ``signature``,
    ``session_id`` and ``authorization`` (an HTTP header value), with an optional plural
    suffix, optional digits (``password2``) and other words around them. A ``_key`` suffix also matches (``api_key`` /
    ``access_key`` / ``signing_key``), but a field literally named ``key`` does not, so benign
    names like ``keyboard``, ``monkey``, and a plain ``key`` map field are not treated as
    sensitive. Words may be separated by underscores, hyphens, dots or spaces, or by a change of
    case, so ``dbPassword``, ``DBPassword`` and ``client-secret`` match like ``db_password`` and
    ``client_secret``.

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
        >>> is_sensitive("dbPassword"), is_sensitive("client-secret"), is_sensitive("keyBinding")
        (True, True, False)
        >>> is_sensitive("smtp_pass"), is_sensitive("passenger")
        (True, False)
        >>> is_sensitive("password2"), is_sensitive("apiKey1"), is_sensitive("pass2go")
        (True, True, False)
    """
    words = _SEPARATORS.sub("_", _CAMEL_BOUNDARY.sub("_", key))
    return _SENSITIVE_PATTERN.search(words) is not None


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


def is_sensitive_at(
    path: Sequence[str], *, not_sensitive: NotSensitiveKeys | Iterable[str] | None = NotSensitiveKeys.NONE
) -> bool:
    """Return whether the key at *path* is masked: its own name looks secret and nothing declared it.

    Args:
        path: The key's segments from the root, its own name last.
        not_sensitive: Paths the application declared not sensitive: dotted paths, as
            :func:`redact_mapping` and ``read_config`` take them, or a built :class:`NotSensitiveKeys`
            (build it once with :meth:`NotSensitiveKeys.of` when asking about many keys).

    Returns:
        Whether the value at *path* must be treated as a secret.

    Raises:
        TypeError: *path* is a ``str``; a dotted name is not a path, split it first. Or
            *not_sensitive* is a single ``str``, as on the other functions.

    Examples:
        >>> declared = NotSensitiveKeys.of(["performance.max_token_bytes"])
        >>> is_sensitive_at(("performance", "max_token_bytes"), not_sensitive=declared)
        False
        >>> is_sensitive_at(("performance", "max_token_bytes"), not_sensitive=["performance.max_token_bytes"])
        False
        >>> is_sensitive_at(("db", "password"), not_sensitive=declared)
        True
        >>> is_sensitive_at("db.password")
        Traceback (most recent call last):
        ...
        TypeError: path is a sequence of segments, not a dotted str: write tuple('db.password'.split('.'))
    """
    _refuse_str_path(path)
    keys = not_sensitive if isinstance(not_sensitive, NotSensitiveKeys) else NotSensitiveKeys.of(not_sensitive)
    return bool(path) and is_sensitive(path[-1]) and not keys.covers(path)


def redact_value_at(
    path: Sequence[str], value: object, *, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE
) -> Any:
    """Return *value*, found at *path* in a tree, as :func:`redact_mapping` of that tree shows it.

    Only *path* is walked: a key on it whose name looks secret masks everything below it, then
    *value* is redacted by itself. One key of a large configuration so costs that key's depth and
    size, not a copy of the whole tree. Nesting is counted as in the whole walk, so the mappings
    along *path* and *value* below it are refused at the same depth; nesting elsewhere in the tree
    is not looked at.

    Args:
        path: The key's segments from the root, its own name last.
        value: What the tree holds at *path*; a caller that must not hand out its own containers
            passes a copy, since a value with no secret in it comes back as given.
        not_sensitive: Paths the application declared not sensitive.

    Returns:
        :data:`REDACTED_PLACEHOLDER` when a key on *path* is sensitive, else *value* redacted.

    Raises:
        InvalidFormatError: When the mappings along *path*, or *value*, nest past :data:`_MAX_REDACT_DEPTH`.
        TypeError: *path* is a ``str``.

    Examples:
        >>> redact_value_at(("credentials", "user"), "alice")
        '***REDACTED***'
        >>> redact_value_at(("db",), {"host": "h", "token": "t"})
        {'host': 'h', 'token': '***REDACTED***'}
    """
    _refuse_str_path(path)
    for depth in range(len(path)):
        _ensure_depth(depth)  # the mapping holding path[depth], as the whole walk checks it
        if is_sensitive_at(path[: depth + 1], not_sensitive=not_sensitive):
            return REDACTED_PLACEHOLDER
    return _Redactor(not_sensitive).node(value, path=tuple(path), depth=len(path))


def redact_mapping(data: Mapping[str, Any], *, not_sensitive: Iterable[str] | None = None) -> dict[str, Any]:
    """Return a deep copy of *data* with sensitive values replaced.

    Creates a new dictionary without mutating the input.  Recurses into every
    nested mapping, list and tuple, however they nest, to redact sensitive keys at
    any depth, and masks the password of every URL in a string value whatever its key
    (``scheme://user:pw@host``), unless its path is declared not sensitive.

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

    def mapping(self, mapping: Mapping[str, Any], *, path: tuple[str, ...], depth: int) -> dict[str, Any]:
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
            else:
                result[key] = self.node(value, path=key_path, depth=depth + 1)
        return result

    def node(self, value: object, *, path: tuple[str, ...], depth: int) -> Any:
        """Return *value* (found at *path*) redacted, whatever container holds the secret.

        A mapping of any type is walked by its keys, and a list or tuple item by item keeping its
        type, so a secret inside a list inside a list, or inside a tuple, is reached too. In a string
        every URL with a password keeps everything but the password, unless *path* is declared not
        sensitive. Anything else passes through.

        Raises:
            InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
        """
        if isinstance(value, Mapping):
            return self.mapping(cast("Mapping[str, Any]", value), path=path, depth=depth)
        if isinstance(value, (list, tuple)):
            return self.items(cast("list[Any] | tuple[Any, ...]", value), path=path, depth=depth)
        if isinstance(value, str) and not self.not_sensitive.covers(path):
            return _mask_url_password(value)
        return value

    def items(
        self, items: list[Any] | tuple[Any, ...], *, path: tuple[str, ...], depth: int
    ) -> list[Any] | tuple[Any, ...]:
        """Return *items* (the list or tuple at *path*) with every nested secret redacted.

        An item keeps the container's *path*: a declaration addresses list items without an
        index, at any list depth.

        Raises:
            InvalidFormatError: When nesting exceeds :data:`_MAX_REDACT_DEPTH`.
        """
        _ensure_depth(depth)
        redacted = [self.node(item, path=path, depth=depth + 1) for item in items]
        return tuple(redacted) if isinstance(items, tuple) else redacted


def _mask_url_password(value: str) -> str:
    """Return *value* with the password of every URL in it replaced by :data:`REDACTED_PLACEHOLDER`.

    A value can hold several URLs (a broker failover list ``amqp://u:p1@h1//;amqp://u:p2@h2//``, a URL
    in another URL's query), so each ``scheme://`` starts a URL that runs to the next one, and each is
    masked on its own (:func:`_mask_one_url`); text before the first is kept as it is.

    Examples:
        >>> _mask_url_password("redis://u:p1@h1,redis://u:p2@h2")
        'redis://u:***REDACTED***@h1,redis://u:***REDACTED***@h2'
        >>> _mask_url_password("plain text")
        'plain text'
    """
    starts = _url_starts(value)
    if not starts:
        return value
    ends = [begin for begin, _ in starts[1:]] + [len(value)]
    masked = (
        _mask_one_url(value[begin:end], authority - begin) for (begin, authority), end in zip(starts, ends, strict=True)
    )
    return value[: starts[0][0]] + "".join(masked)


def _url_starts(value: str) -> list[tuple[int, int]]:
    """Return where each URL in *value* starts and where its authority starts.

    Each ``://`` closes a scheme, found by walking back from it; the walk stops at the previous ``://``
    (a ``/`` is not a scheme character), so the whole scan reads each character a bounded number of
    times. A ``://`` that sits in the user info of the URL before it belongs to that URL, not to a URL of
    its own: one whose stretch since that URL's authority start holds none of ``/ ? # @ [``, white space,
    ``,`` and ``;`` (the ``://`` already taken as user info aside), and that an ``@`` follows before any
    white space, ``,`` or ``;`` (``postgresql://svc_user://8xK3pQ@db``, ``https://app://x://y@h``). A
    ``://`` with no scheme in front of it belongs to no URL, so it is no "previous URL" for the scheme
    after it (``1://https://u:pw@h``).

    Examples:
        >>> _url_starts("amqp://u:p@h1//;amqp://u:p@h2//")
        [(0, 7), (16, 23)]
        >>> _url_starts("https://app://8xK3pQ@db")
        [(0, 8)]
        >>> _url_starts("postgresql://svc_user://8xK3pQ@db")
        [(0, 13)]
        >>> _url_starts("12:https://u:pw@h")
        [(3, 11)]
        >>> _url_starts("1://https://u:pw@h")
        [(4, 12)]
    """
    scan = _UserInfoScan(value)
    starts: list[tuple[int, int]] = []
    end = value.find(_SCHEME_END)
    while end >= 0:
        after = end + len(_SCHEME_END)
        inside = scan.in_user_info(end, after)  # asked for every ``://``: it reads each stretch once
        begin = None if inside else _scheme_start(value, end)
        if begin is not None:
            starts.append((begin, after))
            scan.open_at(after)
        end = value.find(_SCHEME_END, after)
    return starts


#: What ends a URL's user info for :class:`_UserInfoScan`: the authority's end, the ``@`` before the
#: host, the separators between the URLs of a list, and ``[``. RFC 3986 user info cannot hold a ``[``;
#: it opens an IPv6 host or a markdown link, so a ``://`` after it starts a URL of its own
#: (``http://[::1]:3128|http://u:pw@proxy``).
_USER_INFO_END: Final[re.Pattern[str]] = re.compile(r"[/?#@\s,;\[]")

#: What separates the URLs of a list, so an ``@`` after one belongs to the next URL.
_LIST_SEPARATOR: Final[re.Pattern[str]] = re.compile(r"[\s,;]")


class _UserInfoScan:
    """Answers, for each ``://`` in turn, whether it sits in the user info of the URL before it.

    Each stretch between two ``://`` is searched once, and the next ``@`` and the next list separator
    are found once and kept until the scan passes them, so a value with many ``://`` stays linear.
    """

    __slots__ = ("_at", "_closed", "_from", "_separator", "_value")

    def __init__(self, value: str) -> None:
        self._value = value
        self._from = 0
        self._closed = True
        self._at = value.find("@")
        found = _LIST_SEPARATOR.search(value)
        self._separator = found.start() if found else -1

    def open_at(self, authority: int) -> None:
        """Start the user info of a URL whose authority starts at *authority*."""
        self._from = authority
        self._closed = False

    def in_user_info(self, end: int, after: int) -> bool:
        """Return ``True`` when the ``://`` from *end* to *after* sits in the open URL's user info."""
        if not self._closed and _USER_INFO_END.search(self._value, self._from, end):
            self._closed = True
        self._from = after
        if self._closed:
            return False
        at = self._next_at(after)
        return at >= 0 and not 0 <= self._next_separator(after) < at

    def _next_at(self, start: int) -> int:
        """Return the first ``@`` at or after *start*, or -1; the kept one moves only forward."""
        if 0 <= self._at < start:
            self._at = self._value.find("@", start)
        return self._at

    def _next_separator(self, start: int) -> int:
        """Return the first list separator at or after *start*, or -1; the kept one moves only forward."""
        if 0 <= self._separator < start:
            found = _LIST_SEPARATOR.search(self._value, start)
            self._separator = found.start() if found else -1
        return self._separator


def _scheme_start(value: str, end: int) -> int | None:
    """Return where the scheme closed by the ``://`` at *end* starts, or ``None``.

    A scheme is a letter followed by letters, digits, ``+``, ``.`` or ``-``, with any sub-schemes after
    a ``:`` (``jdbc:mysql``). Walking back from *end*, each sub-scheme that starts with a letter is
    taken; the first one that does not ends the scheme at its first letter (``1https`` gives
    ``https``), or just after it when it has none (``12:https`` gives ``https``).

    Examples:
        >>> _scheme_start("jdbc:mysql://h", 10), _scheme_start("x=12:https://h", 10)
        (0, 5)
        >>> _scheme_start("-1://h", 2) is None
        True
    """
    low = end
    while low > 0 and value[low - 1] in _SCHEME_RUN:
        low -= 1
    begin: int | None = None
    part_end = end
    while True:
        colon = value.rfind(":", low, part_end)
        part_start = low if colon < 0 else colon + 1
        letter = _first_letter(value, part_start, part_end)
        if letter is None:
            return begin
        if letter > part_start or colon < 0:
            return letter
        begin, part_end = part_start, colon


def _first_letter(value: str, start: int, stop: int) -> int | None:
    """Return the index of the first ASCII letter in ``value[start:stop]``, or ``None``."""
    return next((index for index in range(start, stop) if value[index] in string.ascii_letters), None)


def _mask_one_url(url: str, start: int) -> str:
    """Return *url*, whose authority begins at *start*, with its password replaced by the placeholder.

    Two readings of the URL are tried in turn. The first is the one ``urllib.parse`` uses
    (:func:`_urllib_password`); when it finds no password, the second is the one URL parsers that accept
    an unescaped ``/``, ``?`` or ``#`` in a password use (SQLAlchemy; :func:`_dsn_password`), because a
    mask stopping where ``urllib`` stops shows the rest of such a password in clear.

    Examples:
        >>> _mask_one_url("postgres://alice:hunter2@db/app", 11)
        'postgres://alice:***REDACTED***@db/app'
        >>> _mask_one_url("postgresql://app:Ab/9+x@db/prod", 13)
        'postgresql://app:***REDACTED***@db/prod'
        >>> _mask_one_url("jdbc:mysql://alice:hunter2@db/app", 13)
        'jdbc:mysql://alice:***REDACTED***@db/app'
        >>> _mask_one_url("postgres://alice@db/app", 11)
        'postgres://alice@db/app'
    """
    span = _urllib_password(url, start) or _dsn_password(url, start)
    if span is None:
        return url
    colon, at = span
    return f"{url[: colon + 1]}{REDACTED_PLACEHOLDER}{url[at:]}"


def _urllib_password(value: str, start: int) -> tuple[int, int] | None:
    """Return the ``(colon, at)`` around the password as ``urllib.parse`` reads it, or ``None``.

    The authority runs to the first ``/``, ``?`` or ``#``; the password runs from the first ``:`` to the
    authority's LAST ``@``, so a password holding ``@`` is masked whole and an ``@`` later in the path or
    query leaves the host shown. An authority whose only ``:`` comes after its ``@`` holds no password in
    this reading.

    Examples:
        >>> _urllib_password("amqp://alice:p@ss@mq/vh", 7)
        (12, 17)
        >>> _urllib_password("smtp://alice@example.com:Ab/9@mail", 7) is None
        True
    """
    authority_end = _first_of(value, _AUTHORITY_END, start)
    at = value.rfind("@", start, authority_end)
    colon = value.find(":", start, at) if at >= 0 else -1
    return (colon, at) if colon >= 0 else None


def _dsn_password(value: str, start: int) -> tuple[int, int] | None:
    """Return the ``(colon, at)`` around a password holding ``/``, ``?`` or ``#``, or ``None``.

    The user name runs to the first ``:``, which must come before any ``/``, ``?`` or ``#``; the password runs to the
    last ``@`` before the query (a ``?`` or ``#`` after the first ``@`` following the ``:``), so an ``@``
    in the query leaves the host shown. Not read as a password: a ``:`` inside an IPv6 literal (``[``),
    a drive letter (a one-letter user name and a "password" starting with ``/``, as in
    ``file://C:/data``), and digits up to the end of the authority (a port,
    ``https://example.com:8443/?to=a@b``).

    Examples:
        >>> _dsn_password("x://app:a/b@db", 4)
        (7, 11)
        >>> _dsn_password("http://[::1]/?n=a@b", 7) is None
        True
        >>> _dsn_password("file://C:/data/alice@example.toml", 7) is None
        True
    """
    colon = value.find(":", start)
    if colon < 0 or _first_of(value, _AUTHORITY_END, start) < colon or "[" in value[start:colon]:
        return None
    first_at = value.find("@", colon + 1)
    if first_at < 0:
        return None
    at = value.rfind("@", colon + 1, _first_of(value, "?#", first_at))
    password = value[colon + 1 : at]
    is_drive = (
        _is_file_scheme(value[: max(start - len(_SCHEME_END), 0)])
        and colon - start == 1
        and value[start].isascii()
        and value[start].isalpha()
        and password.startswith("/")
    )
    if is_drive or _is_port(password):
        return None
    return colon, at


def _is_file_scheme(scheme: str) -> bool:
    """Return ``True`` when *scheme* (with any sub-schemes) names a ``file`` URL, whatever its case."""
    return scheme.rpartition(":")[2].lower() == "file"


def _first_of(value: str, chars: str, start: int) -> int:
    """Return the index of the first of *chars* in *value* from *start*, or ``len(value)`` when none occurs."""
    found = [index for index in (value.find(char, start) for char in chars) if index >= 0]
    return min(found) if found else len(value)


def _is_port(after_colon: str) -> bool:
    """Return ``True`` when *after_colon* is a port that ends the authority, not the start of a password.

    Examples:
        >>> _is_port("8443/?to=a")
        True
        >>> _is_port("1234")
        False
    """
    ends = [index for index in (after_colon.find(char) for char in _AUTHORITY_END) if index >= 0]
    # The masker never gets here with no '/', '?' or '#' after the colon: urllib reads such a password
    # first (fuzzed: 0 of 1,311,111 inputs reach it). The empty arm is a guard for another caller,
    # since min() of an empty list raises ValueError (user decision 2026-11-17, s6 R4-F4).
    digits = after_colon[: min(ends)] if ends else ""
    return digits.isascii() and digits.isdigit()


def _ensure_depth(depth: int) -> None:
    """Refuse a walk deeper than :data:`_MAX_REDACT_DEPTH` with a readable error, not RecursionError."""
    if depth > _MAX_REDACT_DEPTH:
        raise InvalidFormatError(f"Configuration nesting exceeds the maximum depth of {_MAX_REDACT_DEPTH}")
