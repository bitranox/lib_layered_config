"""Shared helpers for assigning nested keys using ``__`` delimiters.

Both dotenv and environment adapters need identical logic for converting
``SERVICE__TIMEOUT`` style keys into nested ``{"service": {"timeout": ...}}``
structures. This module centralises that logic to eliminate duplication.

Contents:
    - ``NestedEntry``: one variable to place, with the label a refusal names it by.
    - ``build_nested``: place every entry, the same way whatever order they arrive in.
    - ``resolve_key``: case-insensitive key resolution.
    - ``NESTED_KEY_DELIMITER``: constant for the ``__`` separator.

Used by ``adapters.dotenv.default`` and ``adapters.env.default`` to share
the nested key assignment algorithm.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from ..application.merge import MAX_MERGE_DEPTH, nesting_too_deep

if TYPE_CHECKING:
    from collections.abc import Iterable

NESTED_KEY_DELIMITER: Final[str] = "__"
"""Delimiter used to separate nested key segments in environment variables.

Environment variables like ``SERVICE__TIMEOUT`` are split on this delimiter
to create nested structures like ``{"service": {"timeout": ...}}``.
"""


class NestedEntry(NamedTuple):
    """One variable to place: its ``__`` delimited key, its value, and how a refusal names it."""

    key: str
    value: object
    label: str


class _ScalarBelowError(Exception):
    """Internal signal from :func:`_child_table`: a value sits where a table is needed."""


def build_nested(entries: Iterable[NestedEntry], *, error_cls: type[Exception], where: str = "") -> dict[str, object]:
    """Return the nested mapping *entries* describe, independent of the order they arrive in.

    Shallower keys are placed first, so a JSON object value is a table that deeper keys merge into
    (a deeper key wins over the same key inside the object), and a plain value with a key below it
    is refused whichever comes first. Entries of equal depth keep their order, so a repeated key
    still takes its last value.

    Args:
        entries: Variables in their source order.
        error_cls: Exception type raised when a value sits where a key below it needs a table.
        where: Prefix for the refusal message, such as the file the entries came from.

    Raises:
        error_cls: Naming both variables and the dotted path, never a value; or naming the one
            variable whose key has an empty segment (a leading, trailing or doubled ``__``); or,
            once every key is placed, with the merge's own refusal for a key nesting deeper than
            :data:`MAX_MERGE_DEPTH` (the shallowest such key), built only down to that depth.

    Examples:
        >>> rows = [NestedEntry("DB__PORT", 2, "DB__PORT"), NestedEntry("DB", {"host": "h"}, "DB")]
        >>> build_nested(rows, error_cls=ValueError)
        {'db': {'host': 'h', 'port': 2}}
        >>> build_nested([NestedEntry("DB__PORT", 2, "B"), NestedEntry("DB", "x", "A")], error_cls=ValueError)
        Traceback (most recent call last):
        ...
        ValueError: A sets db to a value, so B cannot set a key below it
        >>> build_nested([NestedEntry("DB____PORT", 2, "APP___DB____PORT")], error_cls=ValueError)
        Traceback (most recent call last):
        ...
        ValueError: APP___DB____PORT has an empty key segment (a leading, trailing or doubled '__')
    """
    ordered = sorted(entries, key=lambda entry: entry.key.count(NESTED_KEY_DELIMITER))
    target: dict[str, object] = {}
    origins: dict[tuple[str, ...], str] = {}
    index = _CaseIndex()
    too_deep: list[str] | None = None
    for entry in ordered:
        parts = _key_parts(entry.key)
        if "" in parts or (_is_too_deep(parts) and _has_empty_segment(parts[-1])):
            # An empty name is a typo, never a table: placed, it replaced a configured value with
            # {"": ...} or set a key nobody reads, and the override looked applied.
            raise error_cls(f"{where}{entry.label} has an empty key segment (a leading, trailing or doubled '__')")
        if too_deep is None and _is_too_deep(parts):
            too_deep = parts[: MAX_MERGE_DEPTH + 1]
        try:
            _assign_parts(target, parts, entry.value, index=index, error_cls=_ScalarBelowError)
        except _ScalarBelowError:
            raise error_cls(where + _collision_message(target, parts, entry.label, origins)) from None
        origins[tuple(part.lower() for part in parts)] = entry.label
    if too_deep is not None:
        raise error_cls(where + nesting_too_deep([part.lower() for part in too_deep]))
    return target


def _key_parts(key: str) -> list[str]:
    """Split *key* at ``__`` into at most the segments the merge places, plus the rest unsplit.

    A key deeper than :data:`MAX_MERGE_DEPTH` allows is refused whatever follows its first levels.
    Splitting all of it, and building a table per segment, cost about 220 bytes per byte of key
    (685 MB for a 3 MB ``.env``) only for the merge to refuse it (user decision 2026-11-16, R3-F2).

    Examples:
        >>> _key_parts("DB__PORT")
        ['DB', 'PORT']
        >>> parts = _key_parts("__".join(["K"] * 200))
        >>> len(parts), parts[-1][:5]
        (102, 'K__K_')
    """
    return key.split(NESTED_KEY_DELIMITER, MAX_MERGE_DEPTH + 1)


def _is_too_deep(parts: list[str]) -> bool:
    """Whether :func:`_key_parts` left an unsplit rest: the key nests past what the merge accepts."""
    return len(parts) > MAX_MERGE_DEPTH + 1


def _has_empty_segment(text: str) -> bool:
    """Whether splitting *text* at ``__`` gives an empty part, found without building the parts.

    Examples:
        >>> [_has_empty_segment(text) for text in ("a__b", "a____b", "__a", "a__", "a___b")]
        [False, True, True, True, False]
    """
    start = 0
    while (found := text.find(NESTED_KEY_DELIMITER, start)) != -1:
        if found == start:
            return True
        start = found + len(NESTED_KEY_DELIMITER)
    return start == len(text)


def _collision_message(
    target: dict[str, object], parts: list[str], label: str, origins: dict[tuple[str, ...], str]
) -> str:
    """Name the entry that placed the blocking value: the deepest placed entry at or above it."""
    blocked = _blocking_path(target, parts)
    # Every value in target was placed by an entry at or above its path, so this always finds one.
    blocker = next(origins[blocked[:depth]] for depth in range(len(blocked), 0, -1) if blocked[:depth] in origins)
    return f"{blocker} sets {'.'.join(blocked)} to a value, so {label} cannot set a key below it"


def _blocking_path(target: dict[str, object], parts: list[str]) -> tuple[str, ...]:
    """Return the lowercased path of the first non-table on the way to the parent of *parts*."""
    table: dict[str, object] | None = target
    path: list[str] = []
    for part in parts[:-1]:
        if table is None:
            break
        path.append(part.lower())
        table = _as_table(table[resolve_key(table, part)])
    return tuple(path)


def _as_table(value: object) -> dict[str, object] | None:
    """Return *value* as a table, or ``None`` when it is a plain value."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


class _CaseIndex:
    """Lowercase-to-stored key index per table, so a case-insensitive lookup is one dict probe.

    Matching each new key against every key already in its table made N siblings cost N*N/2
    comparisons (30,000 keys: about 10 s). A table's index is built on first use, so a table that
    arrived as a JSON value is indexed too, and the first spelling of a key wins, as with
    :func:`resolve_key`. Each entry holds its table, which keeps that table's ``id`` from being
    reused by a later dict while the index is alive. Valid only while the tables change through
    :meth:`store`.
    """

    def __init__(self) -> None:
        self._tables: dict[int, tuple[dict[str, object], dict[str, str]]] = {}

    def resolve(self, table: dict[str, object], key: str) -> str:
        """Return the stored key matching *key* case-insensitively, or its lowercase form."""
        lower = key.lower()
        return self._index_of(table).get(lower, lower)

    def store(self, table: dict[str, object], key: str, value: object) -> None:
        """Set ``table[key]`` and record *key* under its lowercase form."""
        table[key] = value
        self._index_of(table).setdefault(key.lower(), key)

    def _index_of(self, table: dict[str, object]) -> dict[str, str]:
        entry = self._tables.get(id(table))
        if entry is None:
            index: dict[str, str] = {}
            for existing in table:
                index.setdefault(existing.lower(), existing)
            entry = (table, index)
            self._tables[id(table)] = entry
        return entry[1]


def _assign_parts(
    target: dict[str, object], parts: list[str], value: object, *, index: _CaseIndex, error_cls: type[Exception]
) -> None:
    """Place *value* at the path *parts* names, creating tables on the way; see :func:`build_nested`."""
    cursor = target
    for part in parts[:-1]:
        cursor = _child_table(cursor, part, index=index, error_cls=error_cls)
    index.store(cursor, index.resolve(cursor, parts[-1]), value)


def _child_table(
    mapping: dict[str, object], key: str, *, index: _CaseIndex, error_cls: type[Exception]
) -> dict[str, object]:
    """Return the table at *key*, creating it when missing; refuse a plain value already there."""
    resolved = index.resolve(mapping, key)
    if resolved not in mapping:
        index.store(mapping, resolved, dict[str, object]())
    child = mapping[resolved]
    if not isinstance(child, dict):
        raise error_cls(f"Cannot override scalar with mapping for key {key}")
    return cast("dict[str, object]", child)


def resolve_key(mapping: dict[str, object], key: str) -> str:
    """Return an existing key matching ``key`` case-insensitively, or a new lowercase key.

    Preserve case stability while avoiding duplicates that differ only by case.

    Args:
        mapping: Mutable mapping being inspected.
        key: Incoming key to resolve.

    Returns:
        Existing key name or newly normalised lowercase variant.

    Examples:
        >>> resolve_key({'timeout': 5}, 'TIMEOUT')
        'timeout'
        >>> resolve_key({}, 'Endpoint')
        'endpoint'
    """
    lower = key.lower()
    for existing in mapping:
        if existing.lower() == lower:
            return existing
    return lower


__all__ = [
    "NESTED_KEY_DELIMITER",
    "NestedEntry",
    "build_nested",
    "resolve_key",
]
