"""Immutable configuration value object with provenance tracking.

Provide the "configuration aggregate" described in
``docs/systemdesign/concept.md``: an immutable mapping that preserves both the
final merged values and the metadata explaining *where* every dotted key was
sourced. The application and adapter layers rely on this module to honour the
precedence rules documented for layered configuration.

Contents:
    - ``SourceInfo``: typed dictionary describing layer, path, and dotted key.
    - ``Config``: frozen mapping-like dataclass exposing lookup, provenance, and
      serialisation helpers.
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

from collections.abc import Iterable, Iterator, Mapping
from collections.abc import Mapping as MappingABC
from collections.abc import Mapping as MappingType
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypedDict, TypeGuard, TypeVar, cast

import orjson

from .redaction import redact_mapping

__all__ = ["EMPTY_CONFIG", "OVERRIDE_LAYER", "Config", "SourceInfo"]

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
            ``"user"``, ``"dotenv"``, or ``"env"``).
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
        _data: Mapping containing the merged configuration tree. Stored as a
            ``MappingProxyType`` to prevent mutation.
        _meta: Mapping of dotted keys to :class:`SourceInfo`, allowing provenance
            queries via :meth:`origin`.
    """

    _data: Mapping[str, Any]
    _meta: Mapping[str, SourceInfo]

    def __post_init__(self) -> None:
        """Freeze internal mappings immediately after construction."""
        object.__setattr__(self, "_data", _lock_map(self._data))
        object.__setattr__(self, "_meta", _lock_map(self._meta))

    def __getitem__(self, key: str) -> Any:
        """Return the value stored under a top-level key.

        Consumers expect ``Config`` to behave like a standard mapping.

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
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate over top-level keys in insertion order."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of stored top-level keys."""
        return len(self._data)

    def as_dict(self, *, redact: bool = False) -> dict[str, Any]:
        """Return a deep, mutable copy of the configuration tree.

        Callers occasionally need to serialise or further mutate the data in a
        context that does not require provenance.

        Args:
            redact: When ``True``, sensitive values (passwords, tokens, secrets,
                API keys) are replaced with ``***REDACTED***``.

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
        """
        result = _clone_map(self._data)
        if redact:
            return redact_mapping(result)
        return result

    def to_json(self, *, indent: int | None = None, redact: bool = False) -> str:
        """Serialise the configuration as JSON.

        CLI tooling and documentation examples render the merged configuration
        in JSON to support piping into other scripts.

        Args:
            indent: When set to any non-``None`` value, produces 2-space
                indented output (orjson only supports 2-space indentation).
            redact: When ``True``, sensitive values (passwords, tokens, secrets,
                API keys) are replaced with ``***REDACTED***`` before
                serialisation.

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
        option = orjson.OPT_INDENT_2 if indent is not None else 0
        return orjson.dumps(data, option=option).decode()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key* or a default when the path is missing.

        Layered configuration relies on dotted keys (e.g. ``"db.host"``).
        This helper avoids repetitive traversal code at call sites.

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
        return _follow_path(self._data, key, default)

    def origin(self, key: str) -> SourceInfo | None:
        """Return provenance metadata for *key* when available.

        Operators need to understand which layer supplied a value to debug
        precedence questions.

        Args:
            key: Dotted key in the metadata map.

        Returns:
            Metadata dictionary or ``None`` if the key was never observed.

        Examples:
            >>> meta = {"db.host": {"layer": "app", "path": "/etc/app.toml", "key": "db.host"}}
            >>> cfg = Config({"db": {"host": "localhost"}}, meta)
            >>> cfg.origin("db.host")["layer"]
            'app'
            >>> cfg.origin("missing") is None
            True
        """
        return self._meta.get(key)

    def with_overrides(self, overrides: Mapping[str, Any]) -> Config:
        """Return a new configuration with deep-merged overrides applied.

        Recursively merges *overrides* into the existing data.  When both the
        current configuration and *overrides* contain a mapping at the same key,
        the mappings are merged recursively.  Non-mapping values (scalars, lists)
        in *overrides* replace the corresponding values in the original.

        Args:
            overrides: Mapping of keys and values to merge.

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
        replaced: list[tuple[str, Any]] = []
        merged = _deep_merge(self._data, overrides, replaced=replaced)
        return Config(merged, _override_provenance(self._meta, replaced))


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


def _is_at_or_below(dotted: str, paths: frozenset[str]) -> bool:
    """Whether *dotted* is one of *paths* or lies inside one of them.

    Examples:
        >>> _is_at_or_below("db.host", frozenset({"db"})), _is_at_or_below("dbx", frozenset({"db"}))
        (True, False)
    """
    parts = dotted.split(".")
    return any(".".join(parts[:end]) in paths for end in range(1, len(parts) + 1))


def _override_provenance(meta: Mapping[str, SourceInfo], replaced: list[tuple[str, Any]]) -> dict[str, SourceInfo]:
    """Provenance after a merge: the override for every path it replaced, the old source elsewhere.

    Only a path the merge actually REPLACED changes. Entries at or below it are
    dropped, since those values are gone, and every other entry is kept exactly as
    the loader wrote it, including the ones that are not plain leaves (a table
    inside a list, an empty table).

    Examples:
        >>> meta = {"a.b": {"layer": "app", "path": "/x.toml", "key": "a.b"},
        ...         "c": {"layer": "env", "path": None, "key": "c"}}
        >>> sorted(_override_provenance(meta, [("a", 1)]).items())
        [('a', {'layer': 'override', 'path': None, 'key': 'a'}), ('c', {'layer': 'env', 'path': None, 'key': 'c'})]
    """
    paths = frozenset(path for path, _ in replaced)
    provenance = {key: info for key, info in meta.items() if not _is_at_or_below(key, paths)}
    for path, value in replaced:
        for dotted in _override_keys(value, path):
            provenance[dotted] = SourceInfo(layer=OVERRIDE_LAYER, path=None, key=dotted)
    return provenance


def _lock_map(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a read-only view of *mapping*.

    Internal state must remain immutable to uphold the domain contract.

    Args:
        mapping: Mapping to wrap. A shallow copy protects against caller mutation.

    Returns:
        ``MappingProxyType`` over a copy of the source mapping.

    Examples:
        >>> view = _lock_map({"flag": True})
        >>> view["flag"], isinstance(view, MappingProxyType)
        (True, True)
    """
    return MappingProxyType(dict(mapping))


def _deep_merge(
    base: Mapping[str, Any],
    overrides: Mapping[str, Any],
    *,
    replaced: list[tuple[str, Any]] | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """Recursively merge *overrides* into *base*, returning a new dictionary.

    When both base and overrides have a mapping at the same key, merge
    recursively.  Otherwise the override value replaces the base value.
    Lists, scalars, and other non-mapping values are replaced, not merged.

    Args:
        base: Original mapping.
        overrides: Mapping whose values are merged into *base*.
        replaced: When given, receives ``(dotted_path, value)`` for every slot the
            override REPLACED rather than merged into, so provenance can change
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
            merged[key] = _deep_merge(
                cast("MappingType[str, Any]", base_value),
                cast("MappingType[str, Any]", override_value),
                replaced=replaced,
                prefix=f"{prefix}{key}.",
            )
        else:
            merged[key] = override_value
            if replaced is not None:
                replaced.append((f"{prefix}{key}", override_value))
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
        if not _looks_like_mapping(current):
            return default
        if fragment not in current:
            return default
        current = current[fragment]
    return cast("Any", current)


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


def _looks_like_mapping(value: object) -> TypeGuard[MappingType[str, Any]]:
    """Return ``True`` when *value* is a mapping with string keys.

    Dotted traversal should stop when encountering scalars or non-string-keyed
    mappings to avoid surprising behaviour.

    Examples:
        >>> _looks_like_mapping({"key": 1})
        True
        >>> _looks_like_mapping({1: "value"})
        False
        >>> _looks_like_mapping(["not", "mapping"])
        False
    """
    if not isinstance(value, MappingABC):
        return False
    return all(isinstance(key, str) for key in cast("Iterable[object]", value.keys()))


EMPTY_CONFIG = Config(MappingProxyType({}), MappingProxyType({}))
"""Shared empty configuration used by the composition root and CLI helpers.

Avoids repeated allocations when no layers contribute values. The empty
instance satisfies the domain contract (immutability, provenance available but
empty) and is safe to reuse across contexts.
"""
