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

import json
from collections.abc import Iterable, Iterator, Mapping
from collections.abc import Mapping as MappingABC
from collections.abc import Mapping as MappingType
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypedDict, TypeGuard, TypeVar, cast


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

    def as_dict(self) -> dict[str, Any]:
        """Return a deep, mutable copy of the configuration tree.

        Callers occasionally need to serialise or further mutate the data in a
        context that does not require provenance.

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
        return _clone_map(self._data)

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialise the configuration as JSON.

        CLI tooling and documentation examples render the merged configuration
        in JSON to support piping into other scripts.

        Args:
            indent: Optional indentation level mirroring ``json.dumps`` semantics.

        Returns:
            JSON payload containing the cloned configuration data.

        Examples:
            >>> cfg = Config({"debug": True}, {"debug": {"layer": "env", "path": None, "key": "debug"}})
            >>> cfg.to_json()
            '{"debug":true}'
            >>> "\\n  \\"debug\\"" in cfg.to_json(indent=2)
            True
        """
        return json.dumps(self.as_dict(), indent=indent, separators=(",", ":"), ensure_ascii=False)

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
            >>> cfg = Config({"db": {"host": "localhost"}}, {"db.host": {"layer": "app", "path": None, "key": "db.host"}})
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
        """Return a new configuration with shallow top-level overrides applied.

        CLI helpers allow callers to inject ad-hoc overrides while keeping the
        original snapshot intact. This method produces that variant.

        Args:
            overrides: Top-level keys and values to override.

        Returns:
            New configuration instance sharing provenance with the original.

        Examples:
            >>> cfg = Config({"feature": False}, {"feature": {"layer": "app", "path": None, "key": "feature"}})
            >>> cfg.with_overrides({"feature": True})["feature"], cfg["feature"]
            (True, False)
        """
        tinted = _blend_top_level(self._data, overrides)
        return Config(tinted, self._meta)


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


def _blend_top_level(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *base* with *overrides* applied.

    ``Config.with_overrides`` depends on a pure helper so it can reuse
    provenance metadata without mutation.

    Args:
        base: Original mapping.
        overrides: Mapping whose keys replace entries in *base*.

    Returns:
        New dictionary with updated top-level values.

    Examples:
        >>> _blend_top_level({"port": 8000}, {"port": 9000})["port"]
        9000
    """
    tinted = dict(base)
    tinted.update(overrides)
    return tinted


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
    return cast(Any, current)


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
        nested = cast(MappingType[str, Any], value)
        return _clone_map(nested)
    if isinstance(value, list):
        items = cast(list[Any], value)
        return [_clone_value(item) for item in items]
    if isinstance(value, set):
        items = cast(set[Any], value)
        return {_clone_value(item) for item in items}
    if isinstance(value, tuple):
        items = cast(tuple[Any, ...], value)
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
    for key in cast(Iterable[object], value.keys()):
        if not isinstance(key, str):
            return False
    return True


EMPTY_CONFIG = Config(MappingProxyType({}), MappingProxyType({}))
"""Shared empty configuration used by the composition root and CLI helpers.

Avoids repeated allocations when no layers contribute values. The empty
instance satisfies the domain contract (immutability, provenance available but
empty) and is safe to reuse across contexts.
"""
