"""Merge ordered configuration layers while keeping provenance crystal clear.

Purpose
-------
Implement the merge policy described in ``docs/systemdesign/concept.md`` by
folding a sequence of layer snapshots into a single mapping plus provenance.
Preserves the "last writer wins" rule without mutating caller-provided data.

Contents
--------
- ``LayerSnapshot``: immutable record describing a layer name, payload, and
  origin path.
- ``merge_layers``: public API returning merged data and provenance mappings.
- Internal helpers (``_weave_layer``, ``_descend`` …) that manage recursive
  merging, branch clearing, and dotted-key generation.

System Role
-----------
The composition root assembles layer snapshots and delegates to
``merge_layers`` before building the domain ``Config`` value object.
Adapters and CLI code depend on the provenance structure to explain precedence.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from typing import Iterable, Mapping as TypingMapping, Sequence, TypeGuard, cast

from .ports import SourceInfoPayload


@dataclass(frozen=True, eq=False, slots=True)
class LayerSnapshot:
    """Immutable description of a configuration layer.

    Why
    ----
    Keeps layer metadata compact and explicit so merge logic can reason about
    precedence without coupling to adapter implementations.

    Attributes
    ----------
    name:
        Logical name of the layer (``"defaults"``, ``"app"``, ``"host"``,
        ``"user"``, ``"dotenv"``, ``"env"``).
    payload:
        Mapping produced by adapters; expected to contain only JSON-serialisable
        types.
    origin:
        Optional filesystem path (or ``None`` for in-memory sources).
    """

    name: str
    payload: Mapping[str, object]
    origin: str | None


def merge_layers(layers: Iterable[LayerSnapshot]) -> tuple[dict[str, object], dict[str, SourceInfoPayload]]:
    """Merge ordered layers into data and provenance dictionaries.

    Why
    ----
    Central policy point for layered configuration. Ensures later layers may
    override earlier ones and that provenance stays aligned with the final data.

    Parameters
    ----------
    layers:
        Iterable of :class:`LayerSnapshot` instances in merge order (lowest to
        highest precedence).

    Returns
    -------
    tuple[dict[str, object], dict[str, SourceInfoPayload]]
        The merged configuration mapping and provenance mapping keyed by dotted
        path.

    Examples
    --------
    >>> base = LayerSnapshot("app", {"db": {"host": "localhost"}}, "/etc/app.toml")
    >>> override = LayerSnapshot("env", {"db": {"host": "prod"}}, None)
    >>> data, provenance = merge_layers([base, override])
    >>> data["db"]["host"], provenance["db.host"]["layer"]
    ('prod', 'env')
    """

    merged: dict[str, object] = {}
    provenance: dict[str, SourceInfoPayload] = {}

    for snapshot in layers:
        _weave_layer(merged, provenance, snapshot)

    return merged, provenance


def _weave_layer(
    target: MutableMapping[str, object],
    provenance: MutableMapping[str, SourceInfoPayload],
    snapshot: LayerSnapshot,
) -> None:
    """Clone snapshot payload and fold it into accumulators.

    Why
    ----
    Provide a single entry point that ensures each snapshot is processed with
    defensive cloning before descending into nested structures.

    Parameters
    ----------
    target:
        Mutable mapping accumulating merged configuration values.
    provenance:
        Mutable mapping capturing dotted-path provenance entries.
    snapshot:
        Layer snapshot being merged into the accumulators.

    Side Effects
    ------------
    Mutates *target* and *provenance* in place.

    Examples
    --------
    >>> merged, prov = {}, {}
    >>> snap = LayerSnapshot('env', {'flag': True}, None)
    >>> _weave_layer(merged, prov, snap)
    >>> merged['flag'], prov['flag']['layer']
    (True, 'env')
    """

    _descend(target, provenance, snapshot.payload, snapshot, [])


def _descend(
    target: MutableMapping[str, object],
    provenance: MutableMapping[str, SourceInfoPayload],
    incoming: Mapping[str, object],
    snapshot: LayerSnapshot,
    segments: list[str],
) -> None:
    """Walk each key/value pair, updating scalars or branches as needed.

    Why
    ----
    Implements the recursive merge algorithm that honours nested structures and
    ensures provenance stays aligned with the final data.

    Parameters
    ----------
    target:
        Mutable mapping receiving merged values.
    provenance:
        Mutable mapping storing provenance per dotted path.
    incoming:
        Mapping representing the current layer payload.
    snapshot:
        Layer metadata used for provenance entries.
    segments:
        Accumulated path segments used to compute dotted keys during recursion.

    Side Effects
    ------------
    Mutates *target* and *provenance* as it walks through *incoming*.
    """

    for key, value in incoming.items():
        dotted = _join_segments(segments, key)
        if _looks_like_mapping(value):
            _store_branch(target, provenance, key, value, dotted, snapshot, segments)
        else:
            _store_scalar(target, provenance, key, value, dotted, snapshot)


def _store_branch(
    target: MutableMapping[str, object],
    provenance: MutableMapping[str, SourceInfoPayload],
    key: str,
    value: Mapping[str, object],
    dotted: str,
    snapshot: LayerSnapshot,
    segments: list[str],
) -> None:
    """Ensure a nested mapping exists before descending into it.

    Parameters
    ----------
    target:
        Mutable mapping currently being merged into.
    provenance:
        Provenance accumulator updated as recursion progresses.
    key:
        Current key being processed.
    value:
        Mapping representing the nested branch from the incoming layer.
    dotted:
        Dotted representation of the branch path for provenance updates.
    snapshot:
        Metadata describing the active layer.
    segments:
        Mutable list containing the path segments of the current recursion.

    Side Effects
    ------------
    Mutates *target*, *provenance*, and *segments* while recursing.

    Examples
    --------
    >>> target, prov = {}, {}
    >>> branch_snapshot = LayerSnapshot('env', {'child': {'enabled': True}}, None)
    >>> _store_branch(target, prov, 'child', {'enabled': True}, 'child', branch_snapshot, [])
    >>> target['child']['enabled']
    True
    """

    branch = _ensure_branch(target, key)
    segments.append(key)
    _descend(branch, provenance, value, snapshot, segments)
    segments.pop()
    _clear_branch_if_empty(branch, dotted, provenance)


def _store_scalar(
    target: MutableMapping[str, object],
    provenance: MutableMapping[str, SourceInfoPayload],
    key: str,
    value: object,
    dotted: str,
    snapshot: LayerSnapshot,
) -> None:
    """Set the scalar value and update provenance in lockstep.

    Parameters
    ----------
    target:
        Mutable mapping receiving the scalar value.
    provenance:
        Mutable mapping storing provenance metadata.
    key:
        Immediate key to update within *target*.
    value:
        Value drawn from the incoming layer.
    dotted:
        Fully-qualified dotted key for provenance lookups.
    snapshot:
        Metadata describing the active layer.

    Side Effects
    ------------
    Mutates both *target* and *provenance*.

    Examples
    --------
    >>> target, prov = {}, {}
    >>> snap = LayerSnapshot('env', {'flag': True}, None)
    >>> _store_scalar(target, prov, 'flag', True, 'flag', snap)
    >>> target['flag'], prov['flag']['layer']
    (True, 'env')
    """

    target[key] = _clone_leaf(value)
    provenance[dotted] = {
        "layer": snapshot.name,
        "path": snapshot.origin,
        "key": dotted,
    }


def _clone_leaf(value: object) -> object:
    """Return a defensive copy of mutable leaf values.

    Why
    ----
    Prevents callers from mutating adapter-provided data after the merge,
    preserving immutability guarantees described in the system design.

    Parameters
    ----------
    value:
        Leaf value drawn from the incoming layer.

    Returns
    -------
    object
        Clone of the input value; immutable types are returned unchanged.

    Examples
    --------
    >>> original = {'items': [1, 2]}
    >>> cloned = _clone_leaf(original)
    >>> cloned is original
    False
    >>> cloned['items'][0] = 42
    >>> original['items'][0]
    1
    """

    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        return {key: _clone_leaf(item) for key, item in mapping.items()}
    if isinstance(value, list):
        sequence = cast(list[object], value)
        return [_clone_leaf(item) for item in sequence]
    if isinstance(value, set):
        members = cast(set[object], value)
        return {_clone_leaf(item) for item in members}
    if isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
        return tuple(_clone_leaf(item) for item in items)
    return value


def _ensure_branch(target: MutableMapping[str, object], key: str) -> MutableMapping[str, object]:
    """Return an existing branch or create a fresh empty one.

    Parameters
    ----------
    target:
        Mutable mapping holding the current branch.
    key:
        Key that should reference a nested mapping.

    Returns
    -------
    MutableMapping[str, object]
        Existing branch when present or a new one inserted into *target*.

    Side Effects
    ------------
    Inserts a new mutable mapping into *target* when needed.

    Examples
    --------
    >>> branch = _ensure_branch({}, 'child')
    >>> isinstance(branch, MutableMapping)
    True
    >>> second = _ensure_branch({'child': branch}, 'child')
    >>> second is branch
    True
    """

    current = target.get(key)
    if _looks_like_mapping(current):
        return cast(MutableMapping[str, object], current)

    new_branch: MutableMapping[str, object] = {}
    target[key] = new_branch
    return new_branch


def _clear_branch_if_empty(
    branch: MutableMapping[str, object], dotted: str, provenance: MutableMapping[str, SourceInfoPayload]
) -> None:
    """Remove empty branches from provenance when overwritten by scalars.

    Parameters
    ----------
    branch:
        Mutable mapping representing the nested branch just processed.
    dotted:
        Dotted key corresponding to the branch.
    provenance:
        Provenance mapping to prune when the branch becomes empty.

    Side Effects
    ------------
    Mutates *provenance* by removing entries when the branch no longer has data.

    Examples
    --------
    >>> prov = {'a.b': {'layer': 'env', 'path': None, 'key': 'a.b'}}
    >>> _clear_branch_if_empty({}, 'a.b', prov)
    >>> 'a.b' in prov
    False
    """

    if branch:
        return
    provenance.pop(dotted, None)


def _join_segments(segments: Sequence[str], key: str) -> str:
    """Join the current path segments with the new key.

    Parameters
    ----------
    segments:
        Tuple of parent path segments accumulated so far.
    key:
        Current key being appended to the dotted path.

    Returns
    -------
    str
        Dotted path string combining *segments* and *key*.

    Examples
    --------
    >>> _join_segments(('db', 'config'), 'host')
    'db.config.host'
    >>> _join_segments((), 'timeout')
    'timeout'
    """

    if not segments:
        return key
    return ".".join((*segments, key))


def _looks_like_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    """Return ``True`` when *value* is a mapping with string keys.

    Why
    ----
    Guards recursion so scalars are handled separately from nested mappings.

    Parameters
    ----------
    value:
        Candidate object inspected during recursion.

    Returns
    -------
    bool
        ``True`` when *value* behaves like ``Mapping[str, object]``.

    Examples
    --------
    >>> _looks_like_mapping({'a': 1})
    True
    >>> _looks_like_mapping(['not', 'mapping'])
    False
    """

    if not isinstance(value, MappingABC):
        return False
    mapping = cast(TypingMapping[object, object], value)
    keys = cast(Iterable[object], mapping.keys())
    return all(isinstance(k, str) for k in keys)


__all__ = ["LayerSnapshot", "merge_layers"]
