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
from copy import deepcopy
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

    Side Effects
    ------------
    Mutates *target* and *provenance* in place.
    """

    cloned = deepcopy(dict(snapshot.payload))
    _descend(target, provenance, cloned, snapshot, [])


def _descend(
    target: MutableMapping[str, object],
    provenance: MutableMapping[str, SourceInfoPayload],
    incoming: Mapping[str, object],
    snapshot: LayerSnapshot,
    segments: list[str],
) -> None:
    """Walk each key/value pair, updating scalars or branches as needed."""

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
    """Ensure a nested mapping exists, then descend into it."""

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
    """Set the scalar value and update provenance in lockstep."""

    target[key] = value
    provenance[dotted] = {
        "layer": snapshot.name,
        "path": snapshot.origin,
        "key": dotted,
    }


def _ensure_branch(target: MutableMapping[str, object], key: str) -> MutableMapping[str, object]:
    """Return an existing branch or create a fresh empty one."""

    current = target.get(key)
    if _looks_like_mapping(current):
        return cast(MutableMapping[str, object], current)

    new_branch: MutableMapping[str, object] = {}
    target[key] = new_branch
    return new_branch


def _clear_branch_if_empty(
    branch: MutableMapping[str, object], dotted: str, provenance: MutableMapping[str, SourceInfoPayload]
) -> None:
    """Remove empty branches from provenance when overwritten by scalars."""

    if branch:
        return
    provenance.pop(dotted, None)


def _join_segments(segments: Sequence[str], key: str) -> str:
    """Join the current path segments with the new key."""

    if not segments:
        return key
    return ".".join((*segments, key))


def _looks_like_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    """Return ``True`` when *value* is a mapping with string keys."""

    if not isinstance(value, MappingABC):
        return False
    mapping = cast(TypingMapping[object, object], value)
    keys = cast(Iterable[object], mapping.keys())
    return all(isinstance(k, str) for k in keys)


__all__ = ["LayerSnapshot", "merge_layers"]
