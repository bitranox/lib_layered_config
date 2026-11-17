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

import re
from collections.abc import Iterable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import accumulate
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from ..domain.config import OVERRIDE_LAYER
from ..domain.errors import InvalidFormatError
from ..domain.identifiers import Layer
from ..observability import log_warn

if TYPE_CHECKING:
    from ..domain.config import SourceInfo

#: Maximum configuration nesting depth. A crafted or corrupt config could otherwise
#: recurse until Python raises an opaque ``RecursionError``; this bound turns that into a
#: clear ``InvalidFormatError`` well before the interpreter stack limit.
MAX_MERGE_DEPTH: Final[int] = 100

#: How much of the key path a too-deep refusal shows: enough to find the table in the file,
#: bounded because a key can be as long as the file allows.
_DEPTH_KEY_SHOWN: Final[int] = 80

#: A list index is ASCII digits only: ``str.isdigit`` also accepts superscripts and other
#: scripts' digits, which ``int()`` either refuses or reads as a number nobody typed.
_LIST_INDEX_KEY: Final[re.Pattern[str]] = re.compile(r"[0-9]+")

#: More significant digits than any list can have elements; such a key is out of range.
#: Keeps ``int()`` far below its 4300-digit conversion limit.
_MAX_INDEX_DIGITS: Final[int] = 18
_INDEX_BEYOND_ANY_LIST: Final[int] = 10**_MAX_INDEX_DIGITS

#: Layers whose key names lost their case on the way in: an environment variable name and a
#: ``.env`` key are read case-insensitively and arrive in lowercase, so their keys are matched
#: case-insensitively against what the lower layers stored. File layers keep exact keys.
_CASE_FOLDED_LAYERS: Final[frozenset[Layer]] = frozenset({Layer.ENV, Layer.DOTENV})


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
    provenance: dict[str, SourceInfo]


@dataclass(frozen=True, eq=False, slots=True)
class LayerSnapshot:
    """Immutable description of a configuration layer.

    Keeps layer metadata compact and explicit so merge logic can reason about
    precedence without coupling to adapter implementations.

    Attributes:
        name: The layer the payload belongs to.
        payload: Mapping produced by adapters; expected to contain only JSON-serialisable
            types.
        origin: Optional filesystem path (or ``None`` for in-memory sources).
    """

    name: Layer
    payload: Mapping[str, object]
    origin: str | None

    def __post_init__(self) -> None:
        """Refuse a name that is not a :class:`Layer`, here rather than deep in the merge.

        Raises:
            TypeError: *name* is not a member, for instance a plain layer string.
        """
        _refuse_a_non_layer(self.name)

    @classmethod
    def of(cls, name: Layer | str, payload: Mapping[str, object], origin: str | None) -> LayerSnapshot:
        """Build a snapshot from a layer member or its plain name.

        ``Config.origin(...)["layer"]`` hands callers the plain string, so a caller rebuilding
        snapshots from provenance holds ``"user"``, not the member. Provenance also holds values
        that name no layer, and this refuses them: :data:`~lib_layered_config.domain.config.OVERRIDE_LAYER`
        (``"override"``, every key :meth:`Config.with_overrides` set) and any source a caller
        names itself (such as ``"cli"``).

        Args:
            name: The layer, as a member or its plain name.
            payload: Mapping produced by adapters.
            origin: Optional filesystem path (or ``None`` for in-memory sources).

        Returns:
            The snapshot, holding the :class:`Layer` member.

        Raises:
            ValueError: *name* names no layer, ``"override"`` and a caller's own source included.

        Examples:
            >>> LayerSnapshot.of("user", {}, None).name is Layer.USER
            True
        """
        try:
            layer = Layer(name)
        except ValueError:
            layers = ", ".join(repr(member.value) for member in Layer)
            raise ValueError(
                f"{name!r} is not a valid Layer: LayerSnapshot.of takes {layers}; provenance also records "
                f"{OVERRIDE_LAYER!r} for a key Config.with_overrides set and a caller's own source such as 'cli', "
                "and neither can be rebuilt into a snapshot"
            ) from None
        return cls(layer, payload, origin)


def _refuse_a_non_layer(name: object) -> None:
    """Raise when *name* is not a :class:`Layer`; takes ``object`` because that is the case it exists for."""
    if not isinstance(name, Layer):
        raise TypeError(f"LayerSnapshot takes a Layer, not {name!r}: use LayerSnapshot.of to pass its plain name")


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
        >>> from lib_layered_config.domain.identifiers import Layer
        >>> base = LayerSnapshot(Layer.APP, {"db": {"host": "localhost"}}, "/etc/app.toml")
        >>> override = LayerSnapshot(Layer.ENV, {"db": {"host": "prod"}}, None)
        >>> result = merge_layers([base, override])
        >>> result.data["db"]["host"], result.provenance["db.host"]["layer"]
        ('prod', 'env')
    """
    merged: dict[str, object] = {}
    provenance = _Provenance()

    for snapshot in layers:
        _weave_layer(merged, provenance, snapshot)

    return MergeResult(data=merged, provenance=provenance.as_dict())


def _weave_layer(
    target: MutableMapping[str, object],
    provenance: _Provenance,
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
        >>> merged, prov = {}, _Provenance()
        >>> from lib_layered_config.domain.identifiers import Layer
        >>> snap = LayerSnapshot(Layer.ENV, {'flag': True}, None)
        >>> _weave_layer(merged, prov, snap)
        >>> merged['flag'], prov['flag']['layer']
        (True, 'env')
    """
    _descend(target, provenance, snapshot.payload, snapshot, [])


def _descend(
    target: MutableMapping[str, object],
    provenance: _Provenance,
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
        InvalidFormatError: When nesting exceeds :data:`MAX_MERGE_DEPTH`.
    """
    if len(segments) > MAX_MERGE_DEPTH:
        raise InvalidFormatError(_too_deep(snapshot, segments))
    spellings = _StoredSpellings(target) if snapshot.name in _CASE_FOLDED_LAYERS else None
    for incoming_key, value in incoming.items():
        key = incoming_key if spellings is None else spellings.resolve(incoming_key, segments, snapshot)
        dotted = _join_segments(segments, key)
        if _looks_like_mapping(value):
            _store_branch(
                target, provenance=provenance, key=key, value=value, dotted=dotted, snapshot=snapshot, segments=segments
            )
        else:
            _store_scalar(
                target, provenance=provenance, key=key, value=value, dotted=dotted, snapshot=snapshot, segments=segments
            )


def _too_deep(snapshot: LayerSnapshot, segments: Sequence[str]) -> str:
    """Say where *snapshot* nests past :data:`MAX_MERGE_DEPTH`: its file, else its layer, and the key path.

    The key path is cut to :data:`_DEPTH_KEY_SHOWN` characters; its start is what finds the table.

    Examples:
        >>> _too_deep(LayerSnapshot(Layer.ENV, {}, None), ["k0", "k1"])
        'environment: configuration nesting exceeds the maximum depth of 100 at k0.k1'
        >>> _too_deep(LayerSnapshot(Layer.APP, {}, "/etc/demo/config.toml"), ["a" * 100])[-12:]
        'aaaaaaaa ...'
    """
    source = snapshot.origin or ("environment" if snapshot.name is Layer.ENV else snapshot.name.value)
    return f"{source}: {nesting_too_deep(segments)}"


def nesting_too_deep(segments: Sequence[str]) -> str:
    """The refusal for nesting past :data:`MAX_MERGE_DEPTH` at *segments*, without its source.

    Shared with the env and ``.env`` loaders, which refuse a too-deep key before building it, so
    both refusals read the same. The key path is cut to :data:`_DEPTH_KEY_SHOWN` characters.

    Examples:
        >>> nesting_too_deep(["k0", "k1"])
        'configuration nesting exceeds the maximum depth of 100 at k0.k1'
    """
    path = ".".join(segments)
    shown = path if len(path) <= _DEPTH_KEY_SHOWN else f"{path[:_DEPTH_KEY_SHOWN]} ..."
    return f"configuration nesting exceeds the maximum depth of {MAX_MERGE_DEPTH} at {shown}"


class _StoredSpellings:
    """The keys one table already holds, grouped by lowercase form, for a case-folded layer.

    Built once per table visit, so matching each incoming key is one dict probe rather than a scan
    of the table: a large ``.env`` adds thousands of keys to one table.

    Examples:
        >>> snap = LayerSnapshot(Layer.ENV, {}, None)
        >>> _StoredSpellings({"dbPassword": "x"}).resolve("dbpassword", [], snap)
        'dbPassword'
        >>> _StoredSpellings({"host": "x"}).resolve("port", [], snap)
        'port'
    """

    __slots__ = ("_by_lowercase",)

    def __init__(self, target: Mapping[str, object]) -> None:
        """Index *target*'s keys by their lowercase form."""
        self._by_lowercase: dict[str, list[str]] = {}
        for stored in target:
            self._by_lowercase.setdefault(stored.lower(), []).append(stored)

    def resolve(self, key: str, segments: Sequence[str], snapshot: LayerSnapshot) -> str:
        """Return the stored spelling of *key*, or *key* itself when none or several match.

        Two stored spellings (``dbPassword`` and ``DBPASSWORD``) leave the choice open: the key is
        placed as it came, and a ``case_folded_key_ambiguous`` warning names both.
        """
        matches = self._by_lowercase.get(key.lower(), [])
        if len(matches) == 1:
            return matches[0]
        if matches:
            _warn_case_folded_key_ambiguous(_join_segments(segments, key), snapshot, matches)
        return key


def _store_branch(
    target: MutableMapping[str, object],
    *,
    provenance: _Provenance,
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
        >>> target, prov = {}, _Provenance()
        >>> from lib_layered_config.domain.identifiers import Layer
        >>> branch_snapshot = LayerSnapshot(Layer.ENV, {'child': {'enabled': True}}, None)
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

    if isinstance(existing, list):
        _forget_below(provenance, dotted)  # the list's element entries go with the list
    branch = _ensure_branch(target, key, dotted, snapshot)
    segments.append(key)
    _descend(branch, provenance, value, snapshot, segments)
    segments.pop()
    _store_branch_provenance(branch, dotted, provenance, snapshot, parents=segments)


def _all_numeric_keys(value: Mapping[str, object]) -> bool:
    """Return ``True`` when *value* is a non-empty mapping whose keys are all ASCII digit strings.

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
        >>> _all_numeric_keys({chr(0x00B2): 'superscript two'})
        False
    """
    return bool(value) and all(_LIST_INDEX_KEY.fullmatch(key) for key in value)


def _list_index(key: str) -> int:
    """Return the list index an ASCII digit *key* names, ignoring leading zeros.

    A key with more than :data:`_MAX_INDEX_DIGITS` significant digits names no reachable slot,
    so it maps to :data:`_INDEX_BEYOND_ANY_LIST` and takes the out-of-range path.

    Examples:
        >>> _list_index('7'), _list_index('007'), _list_index('0' * 5000)
        (7, 7, 0)
        >>> _list_index('1' + '0' * 5000) == _INDEX_BEYOND_ANY_LIST
        True
    """
    digits = _index_digits(key)
    return int(digits) if len(digits) <= _MAX_INDEX_DIGITS else _INDEX_BEYOND_ANY_LIST


def _index_digits(key: str) -> str:
    """Return the ASCII digit *key* without leading zeros: the spelling a slot's paths use.

    ``DS__00__K`` and ``DS__0__K`` address the same slot, so both record provenance under
    ``ds.0.k``; keeping ``00`` left an entry a later ``0`` override never replaced.

    Examples:
        >>> _index_digits('007'), _index_digits('000'), _index_digits('10')
        ('7', '0', '10')
    """
    return key.lstrip("0") or "0"


def _merge_mapping_into_list(
    existing: list[object],
    provenance: _Provenance,
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
    for given_key in sorted(incoming, key=_list_index):
        override = incoming[given_key]
        index = _list_index(given_key)
        index_key = _index_digits(given_key)
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
    provenance: _Provenance,
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
    slot is rebuilt from the override, and the entries of what a replaced table or list
    held go with it; a table replaced by a value or a list, or a value or a list replaced by
    a table, logs ``type_conflict`` as the same change on a table key does. Provenance
    follows the table rule: an element table has an entry of its own only while it is empty.

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
    old_kind = _kind_of(element)  # read before the checks below narrow *element*
    held_value = element is not None
    if _looks_like_mapping(element) and _looks_like_mapping(override):
        table = cast("MutableMapping[str, object]", element)
        segments.append(index_key)
        _descend(table, provenance, override, snapshot, segments)
        segments.pop()
        _store_branch_provenance(table, dotted, provenance, snapshot, parents=segments)
        return table
    if isinstance(element, list) and _looks_like_mapping(override) and _all_numeric_keys(override):
        nested = cast("list[object]", element)
        segments.append(index_key)
        _merge_mapping_into_list(nested, provenance, override, snapshot, segments)
        segments.pop()
        return nested
    new_kind = _kind_of(override)
    if held_value and _swaps_table_kind(old_kind, new_kind):
        _warn_type_conflict(dotted, snapshot, old_kind, new_kind)
    if old_kind is not ValueKind.SCALAR:
        _forget_below(provenance, dotted)  # the keys the replaced container held are gone with it
    return _build_new_element(
        override, provenance=provenance, dotted=dotted, snapshot=snapshot, segments=segments, index_key=index_key
    )


def _swaps_table_kind(old_kind: ValueKind, new_kind: ValueKind) -> bool:
    """Whether a table is replaced by a value or a list, or a value or a list by a table.

    The key-level ``type_conflict`` rule (:func:`_store_scalar`, :func:`_ensure_branch`), applied to
    a list slot too; a slot holding ``None`` warns as little as an absent key does.

    Examples:
        >>> _swaps_table_kind(ValueKind.MAPPING, ValueKind.LIST), _swaps_table_kind(ValueKind.LIST, ValueKind.SCALAR)
        (True, False)
    """
    return (old_kind is ValueKind.MAPPING) != (new_kind is ValueKind.MAPPING)


def _build_new_element(
    override: object,
    *,
    provenance: _Provenance,
    dotted: str,
    snapshot: LayerSnapshot,
    segments: list[str],
    index_key: str,
) -> object:
    """Build a fresh list element from *override*, recording provenance per leaf.

    A mapping override is woven into a new dict so nested leaves get their own dotted
    provenance entries, and the dict has an entry of its own only while it is empty (the
    rule :func:`_store_branch_provenance` applies to a table); a scalar (or other leaf)
    is cloned and recorded at *dotted*.

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
        _store_branch_provenance(new_element, dotted, provenance, snapshot, parents=segments)
        return new_element
    provenance.record(dotted, _provenance_entry(dotted, snapshot), parents=segments)
    return _clone_leaf(override)


def _provenance_entry(dotted: str, snapshot: LayerSnapshot) -> SourceInfo:
    """Return the provenance record for a value contributed by *snapshot* at *dotted*.

    The record stores the layer's plain ``.value``, not the member: provenance is handed to
    callers (``Config.origin``) and serialised, where a plain string is the documented shape.
    """
    return {
        "layer": snapshot.name.value,
        "path": snapshot.origin,
        "key": dotted,
    }


def _store_scalar(
    target: MutableMapping[str, object],
    *,
    provenance: _Provenance,
    key: str,
    value: object,
    dotted: str,
    snapshot: LayerSnapshot,
    segments: Sequence[str],
) -> None:
    """Set the scalar value and update provenance in lockstep.

    Warns when a mapping is being replaced by a scalar or a list, naming the kinds, as
    this may indicate a configuration schema mismatch between layers.
    """
    current = target.get(key)
    if _looks_like_mapping(current):
        _warn_type_conflict(dotted, snapshot, ValueKind.MAPPING, _kind_of(value))
    if _looks_like_mapping(current) or isinstance(current, list):
        _forget_below(provenance, dotted)  # the keys the container held are gone with it

    target[key] = _clone_leaf(value)
    provenance.record(dotted, _provenance_entry(dotted, snapshot), parents=segments)


def _kind_of(value: object) -> ValueKind:
    """The kind a ``type_conflict`` warning reports for *value*.

    Examples:
        >>> [_kind_of(value).value for value in ({"a": 1}, [1], "x")]
        ['mapping', 'list', 'scalar']
    """
    if _looks_like_mapping(value):
        return ValueKind.MAPPING
    return ValueKind.LIST if isinstance(value, list) else ValueKind.SCALAR


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

    Warns when a scalar or a list is being replaced by a mapping, naming the kinds, as
    this may indicate a configuration schema mismatch between layers.
    """
    current = target.get(key)
    if _looks_like_mapping(current):
        return cast("MutableMapping[str, object]", current)

    if current is not None:
        _warn_type_conflict(dotted, snapshot, _kind_of(current), ValueKind.MAPPING)

    new_branch: MutableMapping[str, object] = {}
    target[key] = new_branch
    return new_branch


def _store_branch_provenance(
    branch: MutableMapping[str, object],
    dotted: str,
    provenance: _Provenance,
    snapshot: LayerSnapshot,
    *,
    parents: Sequence[str],
) -> None:
    """Give a branch an entry of its own only while it is empty.

    An empty dict (e.g., ``console_styles: {}``) has no values to carry an origin, so
    the branch records where it was declared, for display output. A branch with
    content has no entry of its own - its values carry theirs - so an entry left by
    an earlier empty declaration, or by a value this branch replaced, is removed:
    otherwise a table filled entirely by a later layer reports the earlier one.

    Args:
        branch: Mutable mapping representing the nested branch just processed.
        dotted: Dotted key corresponding to the branch.
        provenance: Provenance mapping to update.
        snapshot: Layer metadata used for provenance entries.

    Side Effects:
        Mutates *provenance*: sets the branch's entry when it is empty, else removes it.

    Examples:
        >>> prov = _Provenance()
        >>> from lib_layered_config.domain.identifiers import Layer
        >>> snap = LayerSnapshot(Layer.APP, {'styles': {}}, '/etc/app.toml')
        >>> _store_branch_provenance({}, 'styles', prov, snap, parents=())
        >>> prov['styles']['layer']
        'app'
        >>> _store_branch_provenance({'DEBUG': 'dim'}, 'styles', prov, snap, parents=())
        >>> 'styles' in prov
        False
    """
    if branch:
        provenance.pop(dotted, None)
        return
    provenance.record(dotted, _provenance_entry(dotted, snapshot), parents=parents)


class _Provenance(MutableMapping[str, "SourceInfo"]):
    """Provenance entries plus the tree of paths below each container.

    A container replaced by a later layer must take the entries of every key below it along.
    Scanning all entries for that prefix made N replacements over N entries cost N*N (16,000 of
    them took about 4 s), so :meth:`record` files each path under its parent path and
    :meth:`forget_below` walks the paths below a container. The parents come from the merge's
    real segments, never from the dots in a path: a key NAME may hold dots (a quoted TOML key),
    and cutting the text before every dot made one name of D dots cost memory quadratic in D
    (user decision 2026-11-16, R3-F1). Iteration keeps insertion order, like a dict.

    Examples:
        >>> prov = _Provenance()
        >>> for parents, key in (((), 'a'), (('a',), 'b'), (('a', 'b'), 'c'), ((), 'ab'), ((), 'a.x')):
        ...     dotted = _join_segments(parents, key)
        ...     prov.record(dotted, {'layer': 'app', 'path': None, 'key': dotted}, parents=parents)
        >>> prov.forget_below('a')
        >>> list(prov)
        ['a', 'ab', 'a.x']
    """

    def __init__(self) -> None:
        self._entries: dict[str, SourceInfo] = {}
        self._children: dict[str, set[str]] = {}
        self._parent: dict[str, str] = {}

    def __getitem__(self, key: str) -> SourceInfo:
        return self._entries[key]

    def __setitem__(self, key: str, value: SourceInfo) -> None:
        """Refused: an entry is filed by its parent segments, which only :meth:`record` takes."""
        raise TypeError(f"provenance for {key!r} is written with record(dotted, entry, parents=...)")

    def __delitem__(self, key: str) -> None:
        """Remove *key*'s entry; the path stays filed, as a branch whose values keep their own entries."""
        del self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def record(self, dotted: str, entry: SourceInfo, *, parents: Sequence[str]) -> None:
        """Store *entry* for *dotted*, which is *parents* plus one key, filed under its parents."""
        self._link(dotted, parents)
        self._entries[dotted] = entry

    def forget_below(self, dotted: str) -> None:
        """Remove the entries of every path nested under *dotted*."""
        stack = list(self._children.pop(dotted, ()))
        while stack:
            path = stack.pop()
            self._entries.pop(path, None)
            del self._parent[path]
            stack.extend(self._children.pop(path, ()))

    def as_dict(self) -> dict[str, SourceInfo]:
        """Return the entries as the plain dict :class:`MergeResult` carries."""
        return self._entries

    def _link(self, dotted: str, parents: Sequence[str]) -> None:
        """File *dotted* under its parent path, and each parent under its own, up to one already filed."""
        ends = list(accumulate(len(segment) + 1 for segment in parents))  # each parent path's length plus its dot
        child = dotted
        for end in reversed(ends):
            if child in self._parent:
                return
            parent = dotted[: end - 1]
            self._parent[child] = parent
            self._children.setdefault(parent, set()).add(child)
            child = parent


def _forget_below(provenance: _Provenance, dotted: str) -> None:
    """Remove the entries of every key nested under *dotted*.

    Called when a container is replaced wholesale, so the keys it held no longer
    exist and must not keep reporting an origin.
    """
    provenance.forget_below(dotted)


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

    This indicates a potential configuration schema mismatch: one layer holds a mapping at a key or
    list slot and another a scalar or a list there. *old_type* and *new_type* name the kinds,
    ``mapping``, ``scalar`` or ``list``.
    """
    log_warn(
        "type_conflict",
        key=dotted,
        layer=snapshot.name,
        path=snapshot.origin,
        old_type=old_type,
        new_type=new_type,
    )


def _warn_case_folded_key_ambiguous(dotted: str, snapshot: LayerSnapshot, stored: Sequence[str]) -> None:
    """Emit a warning when an env or ``.env`` key matches several stored spellings.

    The override is placed under the key as it came rather than guessing which spelling it meant.
    """
    log_warn(
        "case_folded_key_ambiguous",
        key=dotted,
        layer=snapshot.name,
        path=snapshot.origin,
        stored=list(stored),
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


__all__ = [
    "MAX_MERGE_DEPTH",
    "LayerSnapshot",
    "MergeResult",
    "ValueKind",
    "merge_layers",
    "nesting_too_deep",
]
