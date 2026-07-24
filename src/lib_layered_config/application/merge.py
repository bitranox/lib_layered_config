"""Merge ordered configuration layers while keeping provenance crystal clear.

Implement the merge policy described in ``docs/systemdesign/concept.md`` by
folding a sequence of layer snapshots into a single mapping plus provenance.
Preserves the "last writer wins" rule without mutating caller-provided data.

Contents:
    - ``LayerSnapshot``: immutable record describing a layer name, payload, and
      origin path.
    - ``merge_layers``: public API returning merged data and provenance mappings.
    - Internal helpers (``_weave_layer``, ``_descend`` ...) that manage recursive
      merging, branch clearing, and dotted-key generation.

System Role:
    The composition root assembles layer snapshots and delegates to
    ``merge_layers`` before building the domain ``Config`` value object.
    Adapters and CLI code depend on the provenance structure to explain precedence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from ..domain.errors import InvalidFormatError
from ..domain.identifiers import Layer
from ..observability import log_warn

if TYPE_CHECKING:
    from .ports import SourceInfoPayload

#: Maximum configuration nesting depth. A crafted or corrupt config could otherwise
#: recurse until Python raises an opaque ``RecursionError``; this bound turns that into a
#: clear ``InvalidFormatError`` well before the interpreter stack limit.
_MAX_MERGE_DEPTH: Final[int] = 100


class ValueKind(str, Enum):
    """Categorical value shape reported in a merge ``type_conflict`` warning.

    Subclasses ``str`` (matching :class:`~lib_layered_config.domain.identifiers.Layer`)
    so the member is its own wire/log string on Python 3.10+, where ``StrEnum`` is
    unavailable.
    """

    MAPPING = "mapping"
    SCALAR = "scalar"
    LIST = "list"


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

    Raises:
        InvalidFormatError: When nesting exceeds :data:`_MAX_MERGE_DEPTH`.
    """
    if len(segments) > _MAX_MERGE_DEPTH:
        raise InvalidFormatError(f"Configuration nesting exceeds the maximum depth of {_MAX_MERGE_DEPTH}")
    for key, value in incoming.items():
        dotted = _join_segments(segments, key)
        if _looks_like_mapping(value):
            _store_branch(
                target, provenance=provenance, key=key, value=value, dotted=dotted, snapshot=snapshot, segments=segments
            )
        else:
            _store_scalar(target, provenance=provenance, key=key, value=value, dotted=dotted, snapshot=snapshot)


def _store_branch(
    target: MutableMapping[str, object],
    *,
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
        >>> _store_branch(
        ...     target, provenance=prov, key='child', value={'enabled': True}, dotted='child',
        ...     snapshot=branch_snapshot, segments=[],
        ... )
        >>> target['child']['enabled']
        True
    """
    existing = target.get(key)
    if isinstance(existing, list) and _all_numeric_keys(value):
        segments.append(key)
        _merge_mapping_into_list(cast("list[object]", existing), provenance, value, snapshot, segments)
        segments.pop()
        return

    branch = _ensure_branch(target, key, dotted, snapshot)
    segments.append(key)
    _descend(branch, provenance, value, snapshot, segments)
    segments.pop()
    _store_provenance_for_empty_branch(branch, dotted, provenance, snapshot)


def _all_numeric_keys(value: Mapping[str, object]) -> bool:
    """Return ``True`` when *value* is a non-empty mapping whose keys are all digit strings.

    A numeric-only mapping arriving on top of an existing list is the signal that the
    caller means to address list elements by index (e.g. ``PREFIX___HOSTS__0__NAME``),
    rather than to replace the list with a dict. Requiring *every* key to be numeric keeps
    a mixed mapping (``{"0": ..., "label": ...}``) on the ordinary replace path, so the
    only behaviour that changes is the previously destructive list-clobber.

    Args:
        value: Incoming mapping from the higher-precedence layer.

    Returns:
        ``True`` when *value* has at least one key and every key is a base-10 digit string.

    Examples:
        >>> _all_numeric_keys({'0': 'a', '1': 'b'})
        True
        >>> _all_numeric_keys({'0': 'a', 'label': 'b'})
        False
        >>> _all_numeric_keys({})
        False
    """
    return bool(value) and all(key.isdigit() for key in value)


def _merge_mapping_into_list(
    existing: list[object],
    provenance: MutableMapping[str, SourceInfoPayload],
    incoming: Mapping[str, object],
    snapshot: LayerSnapshot,
    segments: list[str],
) -> None:
    """Overlay a numeric-key mapping onto *existing* by list index.

    Preserves the surrounding list instead of replacing it with a dict, so a single
    element can be overridden from a higher layer without discarding its siblings.
    Indices are applied in ascending order so appends land deterministically.

    Args:
        existing: List being mutated in place (already a defensive clone owned by the merge).
        provenance: Provenance accumulator updated for each overridden leaf.
        incoming: Numeric-key mapping whose keys are list indices.
        snapshot: Layer metadata used for provenance and warnings.
        segments: Path segments up to and including the list key.

    Side Effects:
        Mutates *existing*, *provenance*, and *segments* while overlaying elements.
    """
    for index_key in sorted(incoming, key=int):
        override = incoming[index_key]
        index = int(index_key)
        dotted = _join_segments(segments, index_key)
        if index < len(existing):
            existing[index] = _merge_list_element(
                existing[index],
                override=override,
                provenance=provenance,
                dotted=dotted,
                snapshot=snapshot,
                segments=segments,
                index_key=index_key,
            )
        elif index == len(existing):
            existing.append(
                _build_new_element(
                    override,
                    provenance=provenance,
                    dotted=dotted,
                    snapshot=snapshot,
                    segments=segments,
                    index_key=index_key,
                )
            )
        else:
            _warn_list_index_out_of_range(dotted, snapshot, index)


def _merge_list_element(
    element: object,
    *,
    override: object,
    provenance: MutableMapping[str, SourceInfoPayload],
    dotted: str,
    snapshot: LayerSnapshot,
    segments: list[str],
    index_key: str,
) -> object:
    """Return the merged value for one existing list slot.

    Deep-merges when both the current element and the override are mappings so that
    setting one field (``dataset.0.dsn``) leaves the element's other fields intact.
    A nested list element with a numeric-key override recurses by index too, so
    ``matrix.0.0`` overrides one cell without flattening the inner list. Otherwise the
    slot is rebuilt from the override.

    Args:
        element: Current value occupying the slot.
        override: Incoming value for the slot.
        provenance: Provenance accumulator updated during the merge.
        dotted: Dotted path of the slot (e.g. ``dataset.0``).
        snapshot: Layer metadata used for provenance entries.
        segments: Path segments up to and including the list key.
        index_key: The numeric index as a string, appended while recursing.

    Returns:
        The merged element (the same mutated container, or a freshly built value).
    """
    if _looks_like_mapping(element) and _looks_like_mapping(override):
        segments.append(index_key)
        _descend(cast("MutableMapping[str, object]", element), provenance, override, snapshot, segments)
        segments.pop()
        return element
    if isinstance(element, list) and _looks_like_mapping(override) and _all_numeric_keys(override):
        nested = cast("list[object]", element)
        segments.append(index_key)
        _merge_mapping_into_list(nested, provenance, override, snapshot, segments)
        segments.pop()
        return nested
    return _build_new_element(
        override, provenance=provenance, dotted=dotted, snapshot=snapshot, segments=segments, index_key=index_key
    )


def _build_new_element(
    override: object,
    *,
    provenance: MutableMapping[str, SourceInfoPayload],
    dotted: str,
    snapshot: LayerSnapshot,
    segments: list[str],
    index_key: str,
) -> object:
    """Build a fresh list element from *override*, recording provenance per leaf.

    A mapping override is woven into a new dict so nested leaves get their own dotted
    provenance entries; a scalar (or other leaf) is cloned and recorded at *dotted*.

    Args:
        override: Incoming value for the new/replacement slot.
        provenance: Provenance accumulator updated during the build.
        dotted: Dotted path of the slot.
        snapshot: Layer metadata used for provenance entries.
        segments: Path segments up to and including the list key.
        index_key: The numeric index as a string, appended while recursing.

    Returns:
        The value to place in the list slot.
    """
    if _looks_like_mapping(override):
        new_element: dict[str, object] = {}
        segments.append(index_key)
        _descend(new_element, provenance, override, snapshot, segments)
        segments.pop()
        return new_element
    provenance[dotted] = _provenance_entry(dotted, snapshot)
    return _clone_leaf(override)


def _provenance_entry(dotted: str, snapshot: LayerSnapshot) -> SourceInfoPayload:
    """Return the provenance record for a value contributed by *snapshot* at *dotted*."""
    return {
        "layer": snapshot.name.value if isinstance(snapshot.name, Layer) else snapshot.name,
        "path": snapshot.origin,
        "key": dotted,
    }


def _store_scalar(
    target: MutableMapping[str, object],
    *,
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
        _warn_type_conflict(dotted, snapshot, ValueKind.MAPPING, ValueKind.SCALAR)

    target[key] = _clone_leaf(value)
    provenance[dotted] = _provenance_entry(dotted, snapshot)


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
        return _clone_dict(cast("dict[str, object]", value))
    if isinstance(value, list):
        return _clone_list(cast("list[object]", value))
    if isinstance(value, set):
        return _clone_set(cast("set[object]", value))
    if isinstance(value, tuple):
        return _clone_tuple(cast("tuple[object, ...]", value))
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
        return cast("MutableMapping[str, object]", current)

    if current is not None:
        _warn_type_conflict(dotted, snapshot, ValueKind.SCALAR, ValueKind.MAPPING)

    new_branch: MutableMapping[str, object] = {}
    target[key] = new_branch
    return new_branch


def _store_provenance_for_empty_branch(
    branch: MutableMapping[str, object],
    dotted: str,
    provenance: MutableMapping[str, SourceInfoPayload],
    snapshot: LayerSnapshot,
) -> None:
    """Store provenance for empty dict values so they show source in display output.

    When a layer defines an empty dict (e.g., ``console_styles: {}``), we still want
    to track where that empty value came from for display purposes.

    Args:
        branch: Mutable mapping representing the nested branch just processed.
        dotted: Dotted key corresponding to the branch.
        provenance: Provenance mapping to update for empty branches.
        snapshot: Layer metadata used for provenance entries.

    Side Effects:
        Mutates *provenance* by adding entry when the branch is empty.

    Examples:
        >>> prov = {}
        >>> snap = LayerSnapshot('app', {'styles': {}}, '/etc/app.toml')
        >>> _store_provenance_for_empty_branch({}, 'styles', prov, snap)
        >>> prov['styles']['layer']
        'app'
    """
    if branch:
        return
    provenance[dotted] = _provenance_entry(dotted, snapshot)


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
    if not isinstance(value, Mapping):
        return False
    mapping = cast("Mapping[object, object]", value)
    keys = cast("Iterable[object]", mapping.keys())
    return all(isinstance(k, str) for k in keys)


def _warn_type_conflict(dotted: str, snapshot: LayerSnapshot, old_type: ValueKind, new_type: ValueKind) -> None:
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


def _warn_list_index_out_of_range(dotted: str, snapshot: LayerSnapshot, index: int) -> None:
    """Emit a warning when a numeric-key override targets a slot past the list end.

    A gap-filling index (beyond ``len``) is skipped rather than sparse-padded with
    ``None``, so this flags the dropped override without corrupting the array.
    """
    log_warn(
        "list_index_out_of_range",
        key=dotted,
        layer=snapshot.name,
        path=snapshot.origin,
        index=index,
    )


__all__ = ["LayerSnapshot", "MergeResult", "merge_layers"]
