"""Domain-level configuration value objects.

Purpose
-------
Anchor the immutable `Config` value object that carries merged configuration and
provenance through the system. This module belongs to the domain layer and
contains no I/O, aligning with the Clean Architecture blueprint documented in
``docs/systemdesign/module_reference.md``.

Contents
--------
* :class:`SourceInfo` – typed metadata structure describing where a key came
  from (layer, path, and dotted key).
* :class:`Config` – ``Mapping`` implementation exposing helper methods for
  introspection, provenance lookups, and functional overrides.
* :func:`_deepcopy_mapping` / :func:`_deepcopy_value` – internal helpers that
  clone nested mappings without relying on ``copy.deepcopy`` (which does not
  handle ``mappingproxy`` objects).
* :data:`EMPTY_CONFIG` – canonical empty instance used when no layer produced
  concrete values.

System Role
-----------
Every consumer call to :func:`lib_layered_config.core.read_config` ultimately
receives an instance of :class:`Config`. The type guarantees immutability,
introspectable provenance, and dotted-path convenience without leaking adapter
concerns into the domain.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping as MappingType, TypedDict, TypeVar, overload


class SourceInfo(TypedDict):
    """Describe the origin of a resolved configuration key.

    Why
    ----
    Tooling (CLI, UI, logging) needs to explain which layer supplied a value to
    justify precedence outcomes.

    What
    ----
    Captures the logical layer, optional filesystem path, and full dotted key
    for each merged entry.

    Attributes
    ----------
    layer:
        Logical layer name (``"app"``, ``"host"``, ``"user"``, ``"dotenv"``, or
        ``"env"``).
    path:
        Concrete filesystem path (if any) that produced the key. ``None`` is
        used for in-memory sources such as environment variables.
    key:
        Fully qualified dotted key (for example ``"service.timeout"``) that
        uniquely identifies the merged value.
    """

    layer: str
    path: str | None
    key: str


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Config(MappingABC[str, Any]):
    """Immutable mapping returned to library consumers.

    Why
    ----
    Callers require a read-only structure that behaves like a dictionary yet
    offers provenance insight and safe override mechanics for tests or
    temporary adjustments.

    What
    ----
    Stores merged configuration data and metadata inside ``MappingProxyType``
    instances, implements the :class:`Mapping` protocol, and exposes helper
    methods tailored to layered configuration.

    Parameters
    ----------
    _data:
        Raw mapping produced by the merge algorithm. It is wrapped in a
        ``mappingproxy`` during initialisation to enforce immutability.
    _meta:
        Mapping from dotted keys to :class:`SourceInfo` describing provenance.

    Examples
    --------
    >>> cfg = Config(
    ...     {"service": {"timeout": 30, "endpoint": "https://api.demo"}},
    ...     {
    ...         "service.timeout": {"layer": "app", "path": "/etc/demo/config.toml", "key": "service.timeout"},
    ...         "service.endpoint": {"layer": "user", "path": "/home/demo/.config/demo/config.toml", "key": "service.endpoint"},
    ...     },
    ... )
    >>> cfg.get("service.timeout")
    30
    >>> cfg.origin("service.endpoint")
    {'layer': 'user', 'path': '/home/demo/.config/demo/config.toml', 'key': 'service.endpoint'}
    >>> cfg.with_overrides({"service": {"timeout": 60}}).get("service.timeout")
    60
    """

    _data: Mapping[str, Any]
    _meta: Mapping[str, SourceInfo]

    def __post_init__(self) -> None:
        """Wrap incoming mappings in ``MappingProxyType`` to guarantee immutability.

        Why
        ----
        Prevent accidental mutation by callers or adapters.

        What
        ----
        Replaces the supplied mappings with ``MappingProxyType`` instances,
        ensuring all subsequent access is read-only.

        Side Effects
        ------------
        Mutates the dataclass fields via ``object.__setattr__`` during
        initialisation only.
        """

        object.__setattr__(self, "_data", _freeze_mapping(self._data))
        object.__setattr__(self, "_meta", _freeze_mapping(self._meta))

    def __getitem__(self, key: str) -> Any:
        """Return the top-level value stored under *key*.

        Why
        ----
        Honour the mapping contract so :class:`Config` behaves like a standard
        dictionary for simple lookups.

        Parameters
        ----------
        key:
            Name of the top-level entry to retrieve.

        Returns
        -------
        Any
            The stored value.

        Examples
        --------
        >>> cfg = Config({"feature": True}, {"feature": {"layer": "env", "path": None, "key": "feature"}})
        >>> cfg["feature"]
        True
        """

        return self._data[key]

    def __iter__(self) -> Iterable[str]:
        """Iterate over the top-level keys of the configuration.

        Why
        ----
        Support iteration constructs (`for` loops, comprehensions) that expect
        mapping semantics.

        Returns
        -------
        Iterable[str]
            Iterator over keys.

        Examples
        --------
        >>> cfg = Config({"service": {}, "logging": {}}, {})
        >>> sorted(list(iter(cfg)))
        ['logging', 'service']
        """

        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of top-level keys available.

        Why
        ----
        Maintain compatibility with ``len(mapping)`` operations.

        Returns
        -------
        int
            Number of top-level keys.

        Examples
        --------
        >>> len(Config({"a": 1, "b": 2}, {}))
        2
        """

        return len(self._data)

    def as_dict(self) -> dict[str, Any]:
        """Construct a deep (mutable) ``dict`` copy of the configuration tree.

            Why
            ----
            Provide callers with a mutable representation for serialisation or
            temporary modifications without affecting the immutable source.

            What
            ----
            Recursively clones nested mappings, lists, sets, and tuples using the
            internal helper functions.

            Returns
            -------
            dict[str, Any]
                Deep copy suitable for mutation or JSON/YAML serialisation.

        Examples
        --------
        >>> cfg = Config({"service": {"timeout": 5}}, {"service.timeout": {"layer": "env", "path": None, "key": "service.timeout"}})
        >>> clone = cfg.as_dict()
        >>> clone["service"]["timeout"] = 10
        >>> cfg.get("service.timeout")
        5
        >>> complex_cfg = Config(
        ...     {"features": {"flags": ["alpha", "beta"], "regions": {"primary", "backup"}}},
        ...     {}
        ... )
        >>> exported = complex_cfg.as_dict()
        >>> exported["features"]["flags"].append("gamma")
        >>> exported["features"]["regions"].remove("primary")
        >>> complex_cfg.as_dict()["features"]["flags"]
        ['alpha', 'beta']
        >>> sorted(complex_cfg.as_dict()["features"]["regions"])
        ['backup', 'primary']
        """

        return _deepcopy_mapping(self._data)

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialise the configuration to JSON using :func:`as_dict` under the hood.

            Why
            ----
            Offer a convenience exporter for debugging and documentation tooling.

            Parameters
            ----------
            indent:
                Optional indentation size passed to :func:`json.dumps`.

            Returns
            -------
            str
                JSON representation of the configuration.

            Examples
            --------
            >>> cfg = Config({"service": {"timeout": 5}}, {"service.timeout": {"layer": "env", "path": None, "key": "service.timeout"}})
        >>> cfg.to_json()
        '{"service":{"timeout":5}}'
        >>> print(cfg.to_json(indent=2))
        {
          "service":{
            "timeout":5
          }
        }
        """

        import json

        return json.dumps(self.as_dict(), indent=indent, separators=(",", ":"), ensure_ascii=False)

    @overload
    def get(self, key: str, *, default: T) -> T:  # type: ignore[override]
        ...

    @overload
    def get(self, key: str, *, default: None = ...) -> Any | None:  # type: ignore[override]
        ...

    def get(self, key: str, *, default: Any = None) -> Any:
        """Resolve *key* as a dotted path and return ``default`` when missing.

        Why
        ----
        Consumers frequently request nested configuration values; dotted access
        prevents repetitive guard code.

        Parameters
        ----------
        key:
            Dotted path (e.g. ``"service.timeout"``).
        default:
            Value returned when the path cannot be resolved.

        Returns
        -------
        Any
            Resolved value or ``default``.

        Examples
        --------
        >>> cfg = Config({"service": {"timeout": 5}}, {"service.timeout": {"layer": "env", "path": None, "key": "service.timeout"}})
        >>> cfg.get("service.timeout")
        5
        >>> cfg.get("missing.path", default="fallback")
        'fallback'
        """

        return _resolve_dotted_path(self._data, key, default)

    def origin(self, key: str) -> SourceInfo | None:
        """Return provenance for *key* or ``None`` when no layer produced it.

        Why
        ----
        Enables tooling to explain configuration precedence outcomes to
        operators and developers.

        Parameters
        ----------
        key:
            Dotted path to inspect.

        Returns
        -------
        SourceInfo | None
            Metadata describing the winning layer or ``None`` if absent.

        Examples
        --------
        >>> cfg = Config({"feature": True}, {"feature": {"layer": "env", "path": None, "key": "feature"}})
        >>> cfg.origin("feature")
        {'layer': 'env', 'path': None, 'key': 'feature'}
        >>> cfg.origin("missing") is None
        True
        """

        return self._meta.get(key)

    def with_overrides(self, overrides: Mapping[str, Any]) -> Config:
        """Produce a shallow copy of the configuration with *overrides* applied.

        Why
        ----
        Facilitate per-test/per-request adjustments without mutating shared
        state.

        Parameters
        ----------
        overrides:
            Mapping of top-level keys to replace.

        Returns
        -------
        Config
            New :class:`Config` instance sharing provenance metadata.

        Side Effects
        ------------
        None; returns a new instance.

        Examples
        --------
        >>> base = Config({"feature": False}, {"feature": {"layer": "env", "path": None, "key": "feature"}})
        >>> base.with_overrides({"feature": True}).get("feature")
        True
        >>> base.get("feature")
        False
        """

        merged = _merge_top_level(self._data, overrides)
        return Config(merged, self._meta)


def _freeze_mapping(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an immutable proxy around *mapping*."""

    return MappingProxyType(dict(mapping))


def _merge_top_level(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Apply *overrides* to *base* and return a fresh mutable mapping."""

    updated = dict(base)
    updated.update(overrides)
    return updated


def _resolve_dotted_path(source: Mapping[str, Any], dotted: str, default: Any) -> Any:
    """Resolve *dotted* within *source*, returning *default* when missing."""

    current: Any = source
    for part in dotted.split("."):
        if not isinstance(current, MappingABC) or part not in current:
            return default
        current = current[part]
    return current


def _deepcopy_mapping(mapping: MappingType[str, Any]) -> dict[str, Any]:
    """Recursively clone a mapping so callers receive a mutable copy.

    Why
    ----
    ``copy.deepcopy`` does not preserve ``mappingproxy`` semantics used by
    :class:`Config`. A custom clone keeps behaviour predictable.

    Parameters
    ----------
    mapping:
        Mapping to duplicate.

    Returns
    -------
    dict[str, Any]
        Deep copy of ``mapping``.

    Examples
    --------
    >>> _deepcopy_mapping({"a": {"b": 1}})["a"]["b"]
    1
    """

    result: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, MappingABC):
            result[key] = _deepcopy_mapping(value)
        elif isinstance(value, list):
            result[key] = [_deepcopy_value(item) for item in value]
        else:
            result[key] = _deepcopy_value(value)
    return result


def _deepcopy_value(value: Any) -> Any:
    """Clone nested values while preserving container types where practical.

    Why
    ----
    Ensure composite data structures survive copying even when the standard
    library would convert them to less specific types.

    Parameters
    ----------
    value:
        Value to clone.

    Returns
    -------
    Any
        Cloned value.

    Examples
    --------
    >>> _deepcopy_value({"nested": [1, 2]})
    {'nested': [1, 2]}
    >>> _deepcopy_value(("a", "b"))
    ('a', 'b')
    """

    if isinstance(value, MappingABC):
        return _deepcopy_mapping(value)
    if isinstance(value, list):
        return [_deepcopy_value(item) for item in value]
    if isinstance(value, (set, tuple)):
        iterable = [_deepcopy_value(item) for item in value]
        return type(value)(iterable)
    return value


#: Shared empty configuration used when no layer produced content. The instance
#: is safe to re-use because :class:`Config` enforces immutability.
EMPTY_CONFIG = Config(MappingProxyType({}), MappingProxyType({}))
"""Canonical empty configuration returned by :func:`lib_layered_config.core.read_config`."""
