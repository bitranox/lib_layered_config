"""Merge ordered configuration layers while keeping provenance crystal clear.

Implement the merge policy described in ``docs/systemdesign/concept.md`` by
folding a sequence of layer snapshots into a single mapping plus provenance.
Preserves the "last writer wins" rule without mutating caller-provided data.

Contents:
    - ``LayerSnapshot``: immutable record describing a layer name, payload, and
      origin path.
    - ``merge_layers``: public API returning merged data and provenance mappings.
    - Internal helpers (``_weave_layer``, ``_descend`` …) that manage recursive
      merging, branch clearing, and dotted-key generation.

System Role:
    The composition root assembles layer snapshots and delegates to
    ``merge_layers`` before building the domain ``Config`` value object.
    Adapters and CLI code depend on the provenance structure to explain precedence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from collections.abc import Mapping as MappingABC
from collections.abc import Mapping as TypingMapping
from dataclasses import dataclass
from typing import TypeGuard, cast

from ..observability import log_warn
from .ports import SourceInfoPayload


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Result of merging configuration layers.

    Provides a structured return type instead of raw tuples, improving
    code readability and enabling better IDE support.

    Attributes:
        data: The merged configuration tree with all layers applied.
        provenance: Provenance metadata keyed by dotted path, explaining which layer
            contributed each final value.
    """

    data: dict[str, object]
    provenance: dict[str, SourceInfoPayload]


@dataclass(frozen=True, eq=False, slots=True)
class LayerSnapshot:
    """Immutable description of a configuration layer.

    Keeps layer metadata compact and explicit so merge logic can reason about
    precedence without coupling to adapter implementations.

    Attributes:
        name: Logical name of the layer (``"defaults"``, ``"app"``, ``"host"``,
            ``"user"``, ``"dotenv"``, ``"env"``).
        payload: Mapping produced by adapters; expected to contain only JSON-serialisable
            types.
        origin: Optional filesystem path (or ``None`` for in-memory sources).
    """

    name: str
    payload: Mapping[str, object]
    origin: str | None


def merge_layers(layers: Iterable[LayerSnapshot]) -> MergeResult:
    """Merge ordered layers into data and provenance dictionaries.

    Central policy point for layered configuration. Ensures later layers may
    override earlier ones and that provenance stays aligned with the final data.

    Args:
        layers: Iterable of :class:`LayerSnapshot` instances in merge order (lowest to
            highest precedence).

    Returns:
        Dataclass containing the merged configuration mapping and provenance
        mapping keyed by dotted path.

    Examples:
        >>> base = LayerSnapshot("app", {"db": {"host": "localhost"}}, "/etc/app.toml")
        >>> override = LayerSnapshot("env", {"db": {"host": "prod"}}, None)
        >>> result = merge_layers([base, override])
        >>> result.data["db"]["host"], result.provenance["db.host"]["layer"]
        ('prod', 'env')
    """
    merged: dict[str, object] = {}
    provenance: dict[str, SourceInfoPayload] = {}

    for snapshot in layers:
        _weave_layer(merged, provenance, snapshot)

    return MergeResult(data=merged, provenance=provenance)


def _weave_layer(
    target: MutableMapping[str, object],
    provenance: MutableMapping[str, SourceInfoPayload],
    snapshot: LayerSnapshot,
) -> None:
    """Clone snapshot payload and fold it into accumulators.

    Provide a single entry point that ensures each snapshot is processed with
    defensive cloning before descending into nested structures.

    Args:
        target: Mutable mapping accumulating merged configuration values.
        provenance: Mutable mapping capturing dotted-path provenance entries.
        snapshot: Layer snapshot being merged into the accumulators.

    Side Effects:
        Mutates *target* and *provenance* in place.

    Examples:
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

    Implements the recursive merge algorithm that honours nested structures and
    ensures provenance stays aligned with the final data.

    Args:
        target: Mutable mapping receiving merged values.
        provenance: Mutable mapping storing provenance per dotted path.
        incoming: Mapping representing the current layer payload.
        snapshot: Layer metadata used for provenance entries.
        segments: Accumulated path segments used to compute dotted keys during recursion.

    Side Effects:
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

    Args:
        target: Mutable mapping currently being merged into.
        provenance: Provenance accumulator updated as recursion progresses.
        key: Current key being processed.
        value: Mapping representing the nested branch from the incoming layer.
        dotted: Dotted representation of the branch path for provenance updates.
        snapshot: Metadata describing the active layer.
        segments: Mutable list containing the path segments of the current recursion.

    Side Effects:
        Mutates *target*, *provenance*, and *segments* while recursing.

    Examples:
        >>> target, prov = {}, {}
        >>> branch_snapshot = LayerSnapshot('env', {'child': {'enabled': True}}, None)
        >>> _store_branch(target, prov, 'child', {'enabled': True}, 'child', branch_snapshot, [])
        >>> target['child']['enabled']
        True
    """
    branch = _ensure_branch(target, key, dotted, snapshot)
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

    Warns when a mapping is being replaced by a scalar, as this may indicate
    a configuration schema mismatch between layers.
    """
    current = target.get(key)
    if _looks_like_mapping(current):
        _warn_type_conflict(dotted, snapshot, "mapping", "scalar")

    target[key] = _clone_leaf(value)
    provenance[dotted] = {
        "layer": snapshot.name,
        "path": snapshot.origin,
        "key": dotted,
    }


def _clone_dict(value: dict[str, object]) -> dict[str, object]:
    """Clone a dictionary recursively."""
    return {k: _clone_leaf(i) for k, i in value.items()}


def _clone_list(value: list[object]) -> list[object]:
    """Clone a list recursively."""
    return [_clone_leaf(i) for i in value]


def _clone_set(value: set[object]) -> set[object]:
    """Clone a set recursively."""
    return {_clone_leaf(i) for i in value}


def _clone_tuple(value: tuple[object, ...]) -> tuple[object, ...]:
    """Clone a tuple recursively."""
    return tuple(_clone_leaf(i) for i in value)


def _clone_leaf(value: object) -> object:
    """Return a defensive copy of mutable leaf values.

    Prevents callers from mutating adapter-provided data after the merge,
    preserving immutability guarantees described in the system design.

    Args:
        value: Leaf value drawn from the incoming layer.

    Returns:
        Clone of the input value; immutable types are returned unchanged.

    Examples:
        >>> original = {'items': [1, 2]}
        >>> cloned = _clone_leaf(original)
        >>> cloned is original
        False
        >>> cloned['items'][0] = 42
        >>> original['items'][0]
        1
    """
    if isinstance(value, dict):
        return _clone_dict(cast(dict[str, object], value))
    if isinstance(value, list):
        return _clone_list(cast(list[object], value))
    if isinstance(value, set):
        return _clone_set(cast(set[object], value))
    if isinstance(value, tuple):
        return _clone_tuple(cast(tuple[object, ...], value))
    return value


def _ensure_branch(
    target: MutableMapping[str, object],
    key: str,
    dotted: str,
    snapshot: LayerSnapshot,
) -> MutableMapping[str, object]:
    """Return an existing branch or create a fresh empty one.

    Warns when a scalar value is being replaced by a mapping, as this may
    indicate a configuration schema mismatch between layers.
    """
    current = target.get(key)
    if _looks_like_mapping(current):
        return cast(MutableMapping[str, object], current)

    if current is not None:
        _warn_type_conflict(dotted, snapshot, "scalar", "mapping")

    new_branch: MutableMapping[str, object] = {}
    target[key] = new_branch
    return new_branch


def _clear_branch_if_empty(
    branch: MutableMapping[str, object], dotted: str, provenance: MutableMapping[str, SourceInfoPayload]
) -> None:
    """Remove empty branches from provenance when overwritten by scalars.

    Args:
        branch: Mutable mapping representing the nested branch just processed.
        dotted: Dotted key corresponding to the branch.
        provenance: Provenance mapping to prune when the branch becomes empty.

    Side Effects:
        Mutates *provenance* by removing entries when the branch no longer has data.

    Examples:
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

    Args:
        segments: Tuple of parent path segments accumulated so far.
        key: Current key being appended to the dotted path.

    Returns:
        Dotted path string combining *segments* and *key*.

    Examples:
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

    Guards recursion so scalars are handled separately from nested mappings.

    Args:
        value: Candidate object inspected during recursion.

    Returns:
        ``True`` when *value* behaves like ``Mapping[str, object]``.

    Examples:
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


def _warn_type_conflict(dotted: str, snapshot: LayerSnapshot, old_type: str, new_type: str) -> None:
    """Emit a warning when a type conflict occurs during merge.

    This indicates a potential configuration schema mismatch where one layer
    defines a key as a scalar and another defines it as a mapping.
    """
    log_warn(
        "type_conflict",
        key=dotted,
        layer=snapshot.name,
        path=snapshot.origin,
        old_type=old_type,
        new_type=new_type,
    )


__all__ = ["LayerSnapshot", "MergeResult", "merge_layers"]
