"""Immutable configuration value object with provenance tracking.

Provide the "configuration aggregate" described in
``docs/systemdesign/concept.md``: an immutable mapping that preserves both the
final merged values and the metadata explaining *where* every dotted key was
sourced. The application and adapter layers rely on this module to honour the
precedence rules documented for layered configuration.

Contents:
    - ``SourceInfo``: typed dictionary describing layer, path, and dotted key.
    - ``Config``: frozen mapping-like dataclass exposing lookup, provenance, and
      serialisation helpers. It owns a deep copy of its data and hands out copies of
      nested containers, so no caller can change it.
    - Internal helpers (``_follow_path``, ``_clone_map`` ...) that keep traversal
      logic pure and testable.
    - ``EMPTY_CONFIG``: canonical empty instance shared across the composition
      root and CLI utilities.

System Role:
    The composition root builds ``Config`` instances after merging layer snapshots.
    Presentation layers (CLI, examples) consume the public API to render human or
    JSON output without re-implementing provenance rules.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from collections.abc import Mapping as MappingABC
from collections.abc import Mapping as MappingType
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, TypedDict, TypeVar, cast

from . import json_codec
from .errors import InvalidFormatError, ValidationError
from .redaction import NotSensitiveKeys, redact_mapping, redact_value_at

__all__ = ["EMPTY_CONFIG", "OVERRIDE_LAYER", "Config", "SourceInfo", "adopt_merged"]

#: Marks "not found" where None is a legitimate stored value.
_MISSING: Final[object] = object()

OVERRIDE_LAYER = "override"
"""The ``layer`` that :meth:`Config.with_overrides` records for every key it supplies.

Not a :class:`~lib_layered_config.domain.identifiers.Layer` member: those name the
sources the loader reads, and an override is applied in code after loading.
"""


class SourceInfo(TypedDict):
    """Describe the provenance of a configuration value.

    Downstream tooling (CLI, deploy helpers) needs to display where a value
    originated so operators can trace precedence decisions.

    Attributes:
        layer: Name of the logical layer (``"defaults"``, ``"app"``, ``"host"``,
            ``"user"``, ``"dotenv"``, or ``"env"``), :data:`OVERRIDE_LAYER` for a key
            :meth:`Config.with_overrides` set, or a source a caller names itself (such as
            ``"cli"``). Always text: ``Config`` stores an enum member as its value.
        path: Absolute filesystem path when known; ``None`` for ephemeral sources
            such as environment variables.
        key: Fully-qualified dotted key corresponding to the stored value.
    """

    layer: str
    path: str | None
    key: str


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Config(MappingABC[str, Any]):
    """Immutable mapping plus provenance metadata for a merged configuration.

    The system design mandates that merged configuration stays read-only after
    assembly so every layer sees a consistent snapshot. ``Config`` enforces that
    contract while providing ergonomic helpers for dotted lookups and
    serialisation.

    Attributes:
        _data: Mapping containing the merged configuration tree. Stored as a deep copy
            in a read-only mapping; reads return copies of nested tables and lists, so a
            caller changing a value it read never changes the ``Config``.
        _meta: Mapping of dotted keys to :class:`SourceInfo`, allowing provenance
            queries via :meth:`origin`.
        _not_sensitive: Paths the application declared not sensitive (``read_config(not_sensitive=...)``);
            redaction leaves them visible. Not compared: two configs with equal data and provenance are equal.
    """

    _data: Mapping[str, Any]
    _meta: Mapping[str, SourceInfo]
    _not_sensitive: NotSensitiveKeys = field(default=NotSensitiveKeys.NONE, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Freeze internal mappings immediately after construction.

        A provenance entry's ``layer`` is stored as text: an enum member (a ``Layer``, or a caller's own
        str-valued enum) is stored as its value, so it reads and prints as ``"user"``, not ``Layer.USER``.
        Each entry is checked here, so a malformed one fails where it was built rather than at a later
        :meth:`origin` call.

        Raises:
            TypeError: ``_not_sensitive`` is not a :class:`NotSensitiveKeys`.
            ValidationError: A provenance entry is not a mapping with exactly ``layer`` (text), ``path``
                (text or ``None``) and ``key`` equal to its own dotted key; the message names the entry.
        """
        if not isinstance(cast("object", self._not_sensitive), NotSensitiveKeys):
            raise TypeError(
                f"Config's third argument must be a NotSensitiveKeys, got {type(self._not_sensitive).__name__}: "
                "use NotSensitiveKeys.of([...])"
            )
        object.__setattr__(self, "_data", _freeze(self._data))
        object.__setattr__(self, "_meta", _ReadOnlyMap(_own_provenance(self._meta)))

    def __getitem__(self, key: str) -> Any:
        """Return the value stored under a top-level key.

        Consumers expect ``Config`` to behave like a standard mapping. A table or list
        comes back as a copy, so changing it leaves the ``Config`` as it was.

        Args:
            key: Top-level key to retrieve.

        Returns:
            Stored value.

        Raises:
            KeyError: When *key* does not exist.

        Examples:
            >>> cfg = Config({"debug": True}, {"debug": {"layer": "env", "path": None, "key": "debug"}})
            >>> cfg["debug"]
            True
        """
        return _clone_value(self._data[key])

    def __contains__(self, key: object) -> bool:
        """Return ``True`` when *key* is a top-level key.

        Answered from the stored keys: the inherited ``Mapping`` test goes through
        :meth:`__getitem__` and so would copy the whole section to answer yes or no.

        Examples:
            >>> cfg = Config({"db": {"host": "localhost"}}, {})
            >>> "db" in cfg, "cache" in cfg
            (True, False)
        """
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        """Iterate over top-level keys in insertion order."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of stored top-level keys."""
        return len(self._data)

    def __repr__(self) -> str:
        """Return the redacted view and a count of the provenance entries, never a secret.

        ``str(config)``, an f-string and a log call's ``%s`` all use this text, so it shows what
        ``as_dict(redact=True)`` shows (declared not-sensitive paths stay visible). Provenance appears only as a
        count: its keys and paths are in :meth:`origin` and ``read_config_json``. A hand-built configuration too
        deeply nested to redact shows its top-level key count instead of its values.

        Examples:
            >>> Config({"db": {"host": "h", "password": "pw"}}, {})
            Config({'db': {'host': 'h', 'password': '***REDACTED***'}}, provenance for 0 keys)
        """
        try:
            redacted = self.as_dict(redact=True)
        except InvalidFormatError:
            shown = f"<{_count(len(self._data), 'top-level key')}, too deeply nested to show>"
        except TypeError:
            # Only a hand-built Config reaches this: every loader refuses a key that is not a string. The
            # repr below stays outside the try, so a value's own failing __repr__ is not reported as this.
            shown = f"<{_count(len(self._data), 'top-level key')}, not shown: a key is not a string>"
        else:
            shown = repr(redacted)
        return f"Config({shown}, provenance for {_count(len(self._meta), 'key')})"

    def as_dict(self, *, redact: bool = False) -> dict[str, Any]:
        """Return a deep, mutable copy of the configuration tree.

        Callers occasionally need to serialise or further mutate the data in a
        context that does not require provenance.

        Args:
            redact: When ``True``, the values of sensitive keys (passwords, tokens,
                secrets, API keys) and the password of every URL in a string value, under
                any key, are replaced with ``***REDACTED***``.

        Returns:
            Independent copy of the configuration data.

        Examples:
            >>> cfg = Config({"debug": True}, {"debug": {"layer": "env", "path": None, "key": "debug"}})
            >>> clone = cfg.as_dict()
            >>> clone["debug"]
            True
            >>> clone["debug"] = False
            >>> cfg["debug"]
            True
            >>> declared = Config({"max_token_bytes": 1}, {}, NotSensitiveKeys.of(["max_token_bytes"]))
            >>> declared.as_dict(redact=True)
            {'max_token_bytes': 1}
        """
        result = _clone_map(self._data)
        if redact:
            return redact_mapping(result, not_sensitive=self._not_sensitive)
        return result

    def to_json(self, *, indent: int | None = None, redact: bool = False) -> str:
        """Serialise the configuration as JSON.

        CLI tooling and documentation examples render the merged configuration
        in JSON to support piping into other scripts.

        Args:
            indent: When set to any non-``None`` value, produces 2-space
                indented output (always a 2-space indent).
            redact: When ``True``, the values of sensitive keys (passwords, tokens,
                secrets, API keys) and the password of every URL in a string value, under
                any key, are replaced with ``***REDACTED***`` before serialisation.

        Returns:
            JSON payload containing the cloned configuration data.

        Examples:
            >>> cfg = Config({"debug": True}, {"debug": {"layer": "env", "path": None, "key": "debug"}})
            >>> cfg.to_json()
            '{"debug":true}'
            >>> "\\n  \\"debug\\"" in cfg.to_json(indent=2)
            True
        """
        data = self.as_dict(redact=redact)
        return json_codec.dumps(data, indent=indent is not None)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key* or a default when the path is missing.

        Layered configuration relies on dotted keys (e.g. ``"db.host"``).
        This helper avoids repetitive traversal code at call sites. A table or list
        comes back as a copy, so changing it leaves the ``Config`` as it was.

        Args:
            key: Dotted path identifying nested entries.
            default: Value to return when the path does not resolve or encounters a
                non-mapping.

        Returns:
            The resolved value or *default* when missing.

        Examples:
            >>> cfg = Config(
            ...     {"db": {"host": "localhost"}}, {"db.host": {"layer": "app", "path": None, "key": "db.host"}}
            ... )
            >>> cfg.get("db.host")
            'localhost'
            >>> cfg.get("db.port", default=5432)
            5432
        """
        value = _follow_path(self._data, key, _MISSING)
        if value is _MISSING:
            return default
        return _clone_value(value)

    def get_redacted(self, key: str, default: Any = None) -> Any:
        """Return the value at dotted *key* as ``as_dict(redact=True)`` shows it.

        A key below a masked section is masked too, so a single key never shows what the
        whole view hides; declared not-sensitive paths stay visible as they do there. Only the
        key's path and value are redacted, so one call costs that key, not a copy of the whole
        configuration, and a value nested too deep elsewhere does not refuse it. The result shares
        no mutable container with the configuration.

        Args:
            key: Dotted path identifying nested entries.
            default: Value to return when *key* does not exist.

        Returns:
            The redacted value, or *default*.

        Examples:
            >>> cfg = Config({"credentials": {"user": "alice"}, "db": {"host": "h"}}, {})
            >>> cfg.get_redacted("credentials.user"), cfg.get_redacted("db.host"), cfg.get_redacted("db.port", 0)
            ('***REDACTED***', 'h', 0)
        """
        value = _follow_path(self._data, key, _MISSING)
        if value is _MISSING:
            return default
        # Copied after redacting, not before: the redactor rebuilds mappings, lists and tuples but
        # hands a set (and anything else it does not walk) back as given, so the copy is still
        # needed, while a path masked whole now skips copying a value it never shows.
        redacted = redact_value_at(tuple(key.split(".")), value, not_sensitive=self._not_sensitive)
        return _clone_value(redacted)

    def origin(self, key: str) -> SourceInfo | None:
        """Return provenance metadata for *key* when available.

        Operators need to understand which layer supplied a value to debug
        precedence questions.

        Args:
            key: Dotted key in the metadata map.

        Returns:
            A copy of the metadata dictionary, or ``None`` if the key was never observed.

        Examples:
            >>> meta = {"db.host": {"layer": "app", "path": "/etc/app.toml", "key": "db.host"}}
            >>> cfg = Config({"db": {"host": "localhost"}}, meta)
            >>> cfg.origin("db.host")["layer"]
            'app'
            >>> cfg.origin("missing") is None
            True
        """
        info = self._meta.get(key)
        return None if info is None else SourceInfo(**info)

    def with_overrides(self, overrides: Mapping[str, Any]) -> Config:
        """Return a new configuration with deep-merged overrides applied.

        Recursively merges *overrides* into the existing data.  When both the
        current configuration and *overrides* contain a mapping at the same key,
        the mappings are merged recursively.  Non-mapping values (scalars, lists)
        in *overrides* replace the corresponding values in the original.

        Args:
            overrides: Mapping of keys and values to merge, nested as the data is:
                ``{"db": {"host": "x"}}``. A key is a name, never a dotted path:
                ``{"db.host": "x"}`` adds a top-level key literally named ``db.host``
                (as a quoted TOML key does) and leaves ``db.host`` unchanged.

        Returns:
            New configuration instance. Every key *overrides* supplies is recorded
            with layer :data:`OVERRIDE_LAYER` and no path, since the value no longer
            comes from the file the old provenance named; every other key keeps its
            original provenance, and keys that no longer exist lose theirs.

        Examples:
            >>> meta = {"db.host": {"layer": "app", "path": "/etc/app.toml", "key": "db.host"},
            ...         "db.port": {"layer": "app", "path": "/etc/app.toml", "key": "db.port"}}
            >>> cfg = Config({"db": {"host": "localhost", "port": 5432}}, meta)
            >>> merged = cfg.with_overrides({"db": {"host": "newhost"}})
            >>> merged["db"]["port"], merged.origin("db.host")["layer"], merged.origin("db.port")["layer"]
            (5432, 'override', 'app')
        """
        trail = _OverrideTrail()
        merged = _deep_merge(self._data, overrides, trail=trail)
        return Config(merged, _override_provenance(self._meta, trail), self._not_sensitive)


class _OverrideTrail:
    """What :func:`_deep_merge` did, for the provenance of the result.

    Attributes:
        replaced: ``(dotted_path, value)`` for every slot the override REPLACED.
        merged_into: ``(dotted_path, table)`` for every table the override merged INTO,
            with the merged table, so its own entry can follow the merge's empty-table rule.

    Examples:
        >>> trail = _OverrideTrail()
        >>> _deep_merge({"a": {}, "b": 1}, {"a": {"x": 1}, "b": 2}, trail=trail)
        {'a': {'x': 1}, 'b': 2}
        >>> trail.replaced, trail.merged_into
        ([('a.x', 1), ('b', 2)], [('a', {'x': 1})])
    """

    __slots__ = ("merged_into", "replaced")

    def __init__(self) -> None:
        self.replaced: list[tuple[str, Any]] = []
        self.merged_into: list[tuple[str, Mapping[str, Any]]] = []


def _override_keys(value: Any, dotted: str) -> Iterator[str]:
    """Yield the keys an override value occupies at *dotted*: its leaves, or *dotted* itself.

    A non-empty table contributes one key per leaf; a scalar, a list or an empty
    table is one value at *dotted*.

    Examples:
        >>> sorted(_override_keys({"b": 1, "c": {"d": [2]}, "e": {}}, "a"))
        ['a.b', 'a.c.d', 'a.e']
        >>> list(_override_keys([1, 2], "a"))
        ['a']
    """
    if isinstance(value, MappingABC) and value:
        for key, child in cast("MappingType[str, Any]", value).items():
            yield from _override_keys(child, f"{dotted}.{key}")
    else:
        yield dotted


def _is_at_or_below(dotted: str, paths: frozenset[str], *, lengths: frozenset[int]) -> bool:
    """Whether *dotted* is one of *paths* or lies inside one of them.

    Only the cuts a path could end at are compared: each length in *lengths* (the lengths of
    *paths*, computed once by the caller) that is the whole key or stops just before a dot.
    Joining the key again at every one of its dots made a key name holding D dots cost D*D time
    (user decision 2026-11-16, R3-F1).

    Examples:
        >>> paths = frozenset({"db"})
        >>> lengths = frozenset(len(path) for path in paths)
        >>> [_is_at_or_below(key, paths, lengths=lengths) for key in ("db", "db.host", "dbx", "d")]
        [True, True, False, False]
    """
    size = len(dotted)
    return any(
        (length == size or (length < size and dotted[length] == ".")) and dotted[:length] in paths for length in lengths
    )


def _override_provenance(meta: Mapping[str, SourceInfo], trail: _OverrideTrail) -> dict[str, SourceInfo]:
    """Provenance after a merge: the override for every path it replaced, the old source elsewhere.

    A path the merge REPLACED changes: entries at or below it are dropped, since
    those values are gone. A table the merge merged INTO follows the merge's rule for
    a table's own entry: it has none once it holds content, and an override that
    declares it empty again is its source. Every other entry is kept exactly as the
    loader wrote it, including the ones that are not plain leaves (a table inside a
    list, an empty table the override did not touch).

    Examples:
        >>> meta = {"a.b": {"layer": "app", "path": "/x.toml", "key": "a.b"},
        ...         "c": {"layer": "env", "path": None, "key": "c"}}
        >>> trail = _OverrideTrail()
        >>> trail.replaced.append(("a", 1))
        >>> sorted(_override_provenance(meta, trail).items())
        [('a', {'layer': 'override', 'path': None, 'key': 'a'}), ('c', {'layer': 'env', 'path': None, 'key': 'c'})]
    """
    paths = frozenset(path for path, _ in trail.replaced)
    lengths = frozenset(len(path) for path in paths)
    provenance = {key: info for key, info in meta.items() if not _is_at_or_below(key, paths, lengths=lengths)}
    for path, value in trail.replaced:
        for dotted in _override_keys(value, path):
            provenance[dotted] = SourceInfo(layer=OVERRIDE_LAYER, path=None, key=dotted)
    for path, table in trail.merged_into:
        if table:
            provenance.pop(path, None)
        else:
            provenance[path] = SourceInfo(layer=OVERRIDE_LAYER, path=None, key=path)
    return provenance


class _ReadOnlyMap(MappingABC[str, Any]):
    """A read-only mapping over a dict nothing else holds, which ``copy`` and ``pickle`` can handle.

    ``MappingProxyType`` refuses both ("cannot pickle 'mappingproxy' object"), which made every
    ``Config`` impossible to copy or pickle. Build one through :func:`_freeze`, never directly.

    Examples:
        >>> view = _freeze({"flag": True})
        >>> view["flag"], view
        (True, {'flag': True})
    """

    __slots__ = ("_items",)

    def __init__(self, items: dict[str, Any]) -> None:
        self._items = items

    def __getitem__(self, key: str) -> Any:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return repr(self._items)

    def __reduce__(self) -> tuple[type[_ReadOnlyMap], tuple[dict[str, Any]]]:
        return (_ReadOnlyMap, (self._items,))


def _freeze(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a read-only mapping over a deep copy of *mapping*.

    A shallow copy left nested tables and lists shared with whoever built the mapping.

    Examples:
        >>> source = {"db": {"host": "real"}}
        >>> frozen = _freeze(source)
        >>> source["db"]["host"] = "changed"
        >>> frozen["db"]["host"]
        'real'
    """
    return _ReadOnlyMap(_clone_map(mapping))


def adopt_merged(data: dict[str, Any], provenance: dict[str, SourceInfo], not_sensitive: NotSensitiveKeys) -> Config:
    """Wrap a merge result's own dicts in a :class:`Config` without copying or checking them again.

    For the library's read path only (``read_config`` and the deploy read), which hands over the
    merge's fresh containers and keeps no reference to them: the merge clones every container it takes
    from a layer and builds each provenance entry itself, in the checked shape with a text ``layer``.
    The result is the same read-only ``Config`` the public constructor builds (reads hand out copies;
    ``copy`` and ``pickle`` work), without its second deep copy. Anything else builds with
    ``Config(...)``, which copies and checks. A module function rather than a private classmethod:
    pyright strict refuses a call to a protected member from outside the class.

    Args:
        data: The merged configuration, owned by nobody else.
        provenance: The merge's provenance, one well-formed entry per leaf, owned by nobody else.
        not_sensitive: The caller's declared not-sensitive paths.

    Returns:
        A :class:`Config` over *data* and *provenance*.

    Examples:
        >>> entry = {"layer": "env", "path": None, "key": "a.b"}
        >>> cfg = adopt_merged({"a": {"b": 1}}, {"a.b": dict(entry)}, NotSensitiveKeys.NONE)
        >>> cfg == Config({"a": {"b": 1}}, {"a.b": dict(entry)})
        True
    """
    adopted = object.__new__(Config)
    object.__setattr__(adopted, "_data", _ReadOnlyMap(data))
    object.__setattr__(adopted, "_meta", _ReadOnlyMap(cast("dict[str, Any]", provenance)))
    object.__setattr__(adopted, "_not_sensitive", not_sensitive)
    return adopted


_ENTRY_KEYS: Final[frozenset[str]] = frozenset({"layer", "path", "key"})


def _own_provenance(meta: Mapping[str, SourceInfo]) -> dict[str, Any]:
    """Return a checked deep copy of *meta* in which every entry's ``layer`` is plain text.

    Raises:
        ValidationError: An entry is not ``SourceInfo``-shaped (see :func:`_own_entry`).

    Examples:
        >>> from lib_layered_config.domain.identifiers import Layer
        >>> _own_provenance({"a": {"layer": Layer.USER, "path": None, "key": "a"}})
        {'a': {'layer': 'user', 'path': None, 'key': 'a'}}
    """
    return {dotted: _own_entry(dotted, info) for dotted, info in meta.items()}


def _own_entry(dotted: str, info: object) -> dict[str, Any]:
    """Return a copy of the provenance entry under *dotted*, an enum member ``layer`` replaced by its value.

    Raises:
        ValidationError: *info* is not a mapping with exactly ``layer`` (text), ``path`` (text or
            ``None``) and ``key`` equal to *dotted*.
    """
    if not isinstance(info, MappingABC):
        raise ValidationError(
            f"provenance entry {dotted!r} must be a mapping with the keys layer, path and key, "
            f"got {type(info).__name__}"
        )
    entry = _clone_map(cast("MappingType[str, Any]", info))
    if frozenset(entry) != _ENTRY_KEYS:
        got = ", ".join(sorted(repr(name) for name in entry))
        raise ValidationError(f"provenance entry {dotted!r} must have exactly the keys layer, path and key, got {got}")
    layer = entry["layer"]
    if isinstance(layer, Enum):
        entry["layer"] = layer = layer.value
    _refuse_a_wrong_field(dotted, entry, layer=layer)
    return entry


def _refuse_a_wrong_field(dotted: str, entry: Mapping[str, Any], *, layer: object) -> None:
    """Raise :class:`ValidationError` when a field of the entry under *dotted* has the wrong type or key."""
    if not isinstance(layer, str):
        raise ValidationError(f"provenance entry {dotted!r}: layer must be text, got {type(layer).__name__}")
    path: object = entry["path"]
    if path is not None and not isinstance(path, str):
        raise ValidationError(f"provenance entry {dotted!r}: path must be text or None, got {type(path).__name__}")
    key: object = entry["key"]
    if key != dotted:
        raise ValidationError(
            f"provenance entry {dotted!r}: key must be {dotted!r}, its own key in the provenance, got {key!r}"
        )


def _deep_merge(
    base: Mapping[str, Any],
    overrides: Mapping[str, Any],
    *,
    trail: _OverrideTrail | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """Recursively merge *overrides* into *base*, returning a new dictionary.

    When both base and overrides have a mapping at the same key, merge
    recursively.  Otherwise the override value replaces the base value.
    Lists, scalars, and other non-mapping values are replaced, not merged.

    Args:
        base: Original mapping.
        overrides: Mapping whose values are merged into *base*.
        trail: When given, receives every slot the override REPLACED rather than
            merged into, and every table it merged into, so provenance can change
            exactly there.
        prefix: Dotted path of *base* inside the whole tree, ending in a dot.

    Returns:
        New dictionary with recursively merged values.

    Examples:
        >>> _deep_merge({"db": {"host": "h", "port": 5432}}, {"db": {"host": "new"}})
        {'db': {'host': 'new', 'port': 5432}}
    """
    merged = dict(base)
    for key, override_value in overrides.items():
        base_value = merged.get(key)
        if isinstance(base_value, MappingABC) and isinstance(override_value, MappingABC):
            table = _deep_merge(
                cast("MappingType[str, Any]", base_value),
                cast("MappingType[str, Any]", override_value),
                trail=trail,
                prefix=f"{prefix}{key}.",
            )
            merged[key] = table
            if trail is not None:
                trail.merged_into.append((f"{prefix}{key}", table))
        else:
            merged[key] = override_value
            if trail is not None:
                trail.replaced.append((f"{prefix}{key}", override_value))
    return merged


def _follow_path(source: Mapping[str, Any], dotted: str, default: Any) -> Any:
    """Traverse *source* using dotted notation.

    Nested configuration should be accessible without exposing internal data
    structures. This helper powers :meth:`Config.get`.

    Args:
        source: Mapping to traverse.
        dotted: Dotted path, e.g. ``"db.host"``.
        default: Fallback when traversal fails.

    Returns:
        Resolved value or *default*.

    Examples:
        >>> payload = {"db": {"host": "localhost"}}
        >>> _follow_path(payload, "db.host", default=None)
        'localhost'
        >>> _follow_path(payload, "db.port", default=5432)
        5432
    """
    current: object = source
    for fragment in dotted.split("."):
        table = _as_table(current)
        if table is None or fragment not in table:
            return default
        current = table[fragment]
    return cast("Any", current)


def _count(number: int, noun: str) -> str:
    """Return *number* with *noun*, plural unless it is one: ``1 key``, ``0 keys``."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _as_table(value: object) -> MappingType[str, Any] | None:
    """Return *value* as a table to walk into, or ``None`` when it is not a mapping.

    A mapping-type check only: a loaded configuration's keys are all strings (every loader refuses
    any other key), so checking each key of every table passed would cost the table's size on every
    lookup for nothing. A dotted fragment is a string, so a non-string key never matches it anyway.

    Examples:
        >>> _as_table({"host": "db"})
        {'host': 'db'}
        >>> _as_table(["not", "a", "table"]) is None
        True
    """
    if isinstance(value, MappingABC):
        return cast("MappingType[str, Any]", value)
    return None


def _clone_map(mapping: MappingType[str, Any]) -> dict[str, Any]:
    """Deep-clone *mapping* while preserving container types.

    ``Config.as_dict`` and JSON serialisation must not leak references to the
    internal immutable structures.

    Args:
        mapping: Mapping to clone.

    Returns:
        Deep copy containing cloned containers and scalar values.

    Examples:
        >>> original = {"levels": (1, 2), "queue": [1, 2]}
        >>> cloned = _clone_map(original)
        >>> cloned["levels"], cloned["queue"]
        ((1, 2), [1, 2])
        >>> cloned["queue"].append(3)
        >>> original["queue"]
        [1, 2]
    """
    sculpted: dict[str, Any] = {}
    for key, value in mapping.items():
        sculpted[key] = _clone_value(value)
    return sculpted


def _clone_value(value: Any) -> Any:
    """Return a clone of *value*, respecting the container type.

    ``_clone_map`` delegates element cloning here so complex structures (lists,
    sets, tuples, nested mappings) remain detached from the immutable source.

    Examples:
        >>> cloned = _clone_value(({"flag": True},))
        >>> cloned
        ({'flag': True},)
        >>> cloned is _clone_value(({"flag": True},))
        False
    """
    if isinstance(value, MappingABC):
        nested = cast("MappingType[str, Any]", value)
        return _clone_map(nested)
    if isinstance(value, list):
        items = cast("list[Any]", value)
        return [_clone_value(item) for item in items]
    if isinstance(value, set):
        items = cast("set[Any]", value)
        return {_clone_value(item) for item in items}
    if isinstance(value, tuple):
        items = cast("tuple[Any, ...]", value)
        return tuple(_clone_value(item) for item in items)
    return value


EMPTY_CONFIG = Config({}, {})
"""Shared empty configuration used by the composition root and CLI helpers.

Avoids repeated allocations when no layers contribute values. The empty
instance satisfies the domain contract (immutability, provenance available but
empty) and is safe to reuse across contexts.
"""
