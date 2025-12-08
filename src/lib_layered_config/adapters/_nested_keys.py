"""Shared helpers for assigning nested keys using ``__`` delimiters.

Both dotenv and environment adapters need identical logic for converting
``SERVICE__TIMEOUT`` style keys into nested ``{"service": {"timeout": ...}}``
structures. This module centralises that logic to eliminate duplication.

Contents:
    - ``assign_nested``: public function to assign a value at a nested key path.
    - ``resolve_key``: case-insensitive key resolution.
    - ``ensure_child_mapping``: ensure intermediate mappings exist.
    - ``NESTED_KEY_DELIMITER``: constant for the ``__`` separator.

Used by ``adapters.dotenv.default`` and ``adapters.env.default`` to share
the nested key assignment algorithm.
"""

from __future__ import annotations

from typing import Final, cast

NESTED_KEY_DELIMITER: Final[str] = "__"
"""Delimiter used to separate nested key segments in environment variables.

Environment variables like ``SERVICE__TIMEOUT`` are split on this delimiter
to create nested structures like ``{"service": {"timeout": ...}}``.
"""


def assign_nested(
    target: dict[str, object],
    key: str,
    value: object,
    *,
    error_cls: type[Exception],
) -> None:
    """Assign ``value`` in ``target`` using case-insensitive ``__`` delimited syntax.

    Args:
        target: Mapping being mutated.
        key: Key using ``__`` separators (e.g., ``SERVICE__TIMEOUT``).
        value: Value to assign at the nested location.
        error_cls: Exception type raised on scalar collisions.

    Side Effects:
        Mutates ``target`` in place.

    Examples:
        >>> data: dict[str, object] = {}
        >>> assign_nested(data, 'SERVICE__TOKEN', 'secret', error_cls=ValueError)
        >>> data
        {'service': {'token': 'secret'}}
    """
    parts = key.split(NESTED_KEY_DELIMITER)
    cursor = target
    for part in parts[:-1]:
        cursor = ensure_child_mapping(cursor, part, error_cls=error_cls)
    final_key = resolve_key(cursor, parts[-1])
    cursor[final_key] = value


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


def ensure_child_mapping(
    mapping: dict[str, object],
    key: str,
    *,
    error_cls: type[Exception],
) -> dict[str, object]:
    """Ensure ``mapping[key]`` is a ``dict``, creating or validating as necessary.

    Prevent accidental overwrites of scalar values when nested keys are introduced.

    Args:
        mapping: Mutable mapping being mutated.
        key: Candidate key to ensure.
        error_cls: Exception type raised when a scalar collision occurs.

    Returns:
        Child mapping stored at the resolved key.

    Side Effects:
        Mutates ``mapping`` by inserting a new child mapping when missing.

    Examples:
        >>> target: dict[str, object] = {}
        >>> child = ensure_child_mapping(target, 'SERVICE', error_cls=ValueError)
        >>> child == {}
        True
        >>> target
        {'service': {}}
    """
    resolved = resolve_key(mapping, key)
    if resolved not in mapping:
        mapping[resolved] = dict[str, object]()
    child = mapping[resolved]
    if not isinstance(child, dict):
        raise error_cls(f"Cannot override scalar with mapping for key {key}")
    typed_child = cast(dict[str, object], child)
    mapping[resolved] = typed_child
    return typed_child


__all__ = ["assign_nested", "resolve_key", "ensure_child_mapping"]
