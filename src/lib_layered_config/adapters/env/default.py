"""Environment variable adapter.

Purpose
-------
Translate process environment variables into nested configuration dictionaries.
It implements the port described in ``docs/systemdesign/module_reference.md``
and forms the final precedence layer in ``lib_layered_config``.

Contents
    - ``default_env_prefix``: canonical prefix builder for a slug.
    - ``DefaultEnvLoader``: orchestrates filtering, coercion, and nesting.
    - ``assign_nested`` / ``_ensure_child_mapping`` / ``_resolve_key``: shared
      helpers re-used by dotenv parsing to keep shapes aligned.
    - ``_coerce`` plus tiny predicate helpers that translate strings into
      Python primitives.
    - ``_normalize_prefix`` / ``_iter_namespace_entries`` / ``_collect_keys``:
      small verbs that keep the loader body declarative.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from typing import cast

from ...observability import log_debug


def default_env_prefix(slug: str) -> str:
    """Return the canonical environment prefix for *slug*.

    Why
    ----
    Namespacing prevents unrelated environment variables from leaking into the
    configuration payload.

    Parameters
    ----------
    slug:
        Package/application slug (typically ``kebab-case``).

    Returns
    -------
    str
        Upper-case prefix with dashes converted to underscores.

    Examples
    --------
    >>> default_env_prefix('lib-layered-config')
    'LIB_LAYERED_CONFIG'
    """

    return slug.replace("-", "_").upper()


class DefaultEnvLoader:
    """Load environment variables that belong to the configuration namespace.

    Why
    ----
    Implements the :class:`lib_layered_config.application.ports.EnvLoader` port,
    translating process environment variables into merge-ready payloads.

    What
    ----
    Filters environment entries by prefix, nests values using ``__`` separators,
    performs primitive coercion, and emits observability events.
    """

    def __init__(self, *, environ: dict[str, str] | None = None) -> None:
        """Initialise the loader with a specific ``environ`` mapping for testability.

        Why
        ----
        Allow tests and callers to supply deterministic environments.

        Parameters
        ----------
        environ:
            Mapping to read from. Defaults to :data:`os.environ`.
        """

        self._environ = os.environ if environ is None else environ

    def load(self, prefix: str) -> dict[str, object]:
        """Return a nested mapping containing variables with the supplied *prefix*.

        Why
        ----
        Environment variables should integrate with the merge pipeline using the
        same nesting semantics as `.env` files.

        What
        ----
        Normalises the prefix, filters matching entries, coerces values, nests
        keys via :func:`assign_nested`, and logs the summarised result.

        Parameters
        ----------
        prefix:
            Prefix filter (upper-case). The loader appends ``_`` if missing.

        Returns
        -------
        dict[str, object]
            Nested mapping suitable for the merge algorithm. Keys are stored in
            lowercase to align with file-based layers.

        Side Effects
        ------------
        Emits ``env_variables_loaded`` debug events with summarised keys.

        Examples
        --------
        >>> env = {
        ...     'DEMO_SERVICE__ENABLED': 'true',
        ...     'DEMO_SERVICE__RETRIES': '3',
        ... }
        >>> loader = DefaultEnvLoader(environ=env)
        >>> payload = loader.load('DEMO')
        >>> payload['service']['retries']
        3
        >>> payload['service']['enabled']
        True
        """

        normalized_prefix = _normalize_prefix(prefix)
        collected: dict[str, object] = {}
        for raw_key, value in _iter_namespace_entries(self._environ.items(), normalized_prefix):
            assign_nested(collected, raw_key, _coerce(value))
        log_debug("env_variables_loaded", layer="env", path=None, keys=_collect_keys(collected))
        return collected


def _normalize_prefix(prefix: str) -> str:
    """Ensure the prefix ends with an underscore when non-empty.

    Why
    ----
    Aligns environment variable filtering semantics regardless of user input.

    Parameters
    ----------
    prefix:
        Raw prefix string (upper-case expected but not enforced).

    Returns
    -------
    str
        Prefix guaranteed to end with ``_`` when non-empty.

    Examples
    --------
    >>> _normalize_prefix('DEMO')
    'DEMO_'
    >>> _normalize_prefix('DEMO_')
    'DEMO_'
    >>> _normalize_prefix('')
    ''
    """

    if prefix and not prefix.endswith("_"):
        return f"{prefix}_"
    return prefix


def _iter_namespace_entries(
    items: Iterable[tuple[str, str]],
    prefix: str,
) -> Iterator[tuple[str, str]]:
    """Yield ``(stripped_key, value)`` pairs that match *prefix*.

    Why
    ----
    Encapsulate prefix filtering so caller code stays declarative.

    Parameters
    ----------
    items:
        Iterable of environment items to examine.
    prefix:
        Normalised prefix (including trailing underscore) to filter on.

    Returns
    -------
    Iterator[tuple[str, str]]
        Pairs whose keys share the prefix with the prefix removed.

    Examples
    --------
    >>> list(_iter_namespace_entries([('DEMO_FLAG', '1'), ('OTHER', '0')], 'DEMO_'))
    [('FLAG', '1')]
    >>> list(_iter_namespace_entries([('DEMO', '1')], 'DEMO_'))
    []
    """

    for key, value in items:
        if prefix and not key.startswith(prefix):
            continue
        stripped = key[len(prefix) :] if prefix else key
        if not stripped:
            continue
        yield stripped, value


def _collect_keys(mapping: dict[str, object]) -> list[str]:
    """Return sorted top-level keys for logging.

    Why
    ----
    Provide compact telemetry context without dumping entire payloads.

    Parameters
    ----------
    mapping:
        Nested mapping produced by environment parsing.

    Returns
    -------
    list[str]
        Sorted list of top-level keys.

    Examples
    --------
    >>> _collect_keys({'service': {}, 'logging': {}})
    ['logging', 'service']
    """

    return sorted(mapping.keys())


def assign_nested(target: dict[str, object], key: str, value: object) -> None:
    """Assign ``value`` inside ``target`` using ``__`` as a nesting delimiter.

    Why
    ----
    Reuse the same semantics as dotenv parsing so callers see consistent shapes.

    What
    ----
    Splits the key on ``__``, ensures intermediate mappings exist, resolves
    case-insensitive keys, and assigns the final value.

    Parameters
    ----------
    target:
        Mapping being mutated in place.
    key:
        Namespaced key using ``__`` separators.
    value:
        Value to store at the resolved path.

    Returns
    -------
    None

    Side Effects
    ------------
    Mutates ``target``.

    Examples
    --------
    >>> data: dict[str, object] = {}
    >>> assign_nested(data, 'SERVICE__TIMEOUT', 5)
    >>> data
    {'service': {'timeout': 5}}
    """

    parts = key.split("__")
    cursor = target
    for part in parts[:-1]:
        cursor = _ensure_child_mapping(cursor, part, error_cls=ValueError)
    final_key = _resolve_key(cursor, parts[-1])
    cursor[final_key] = value


def _resolve_key(mapping: dict[str, object], key: str) -> str:
    """Return an existing key that matches ``key`` (case-insensitive) or a new lowercase key.

    Why
    ----
    Preserve case stability while avoiding duplicates that differ only by case.

    Parameters
    ----------
    mapping:
        Mutable mapping being inspected.
    key:
        Incoming key to resolve.

    Returns
    -------
    str
        Existing key name or newly normalised lowercase variant.

    Examples
    --------
    >>> target = {'timeout': 5}
    >>> _resolve_key(target, 'TIMEOUT')
    'timeout'
    >>> _resolve_key({}, 'Endpoint')
    'endpoint'
    """

    lower = key.lower()
    for existing in mapping.keys():
        if existing.lower() == lower:
            return existing
    return lower


def _ensure_child_mapping(mapping: dict[str, object], key: str, *, error_cls: type[Exception]) -> dict[str, object]:
    """Ensure ``mapping[key]`` is a ``dict`` (creating or validating as necessary).

    Why
    ----
    Prevent accidental overwrites of scalar values when nested keys are
    introduced.

    What
    ----
    Resolves the key case-insensitively, creates an empty mapping when missing,
    or raises ``error_cls`` if a scalar already occupies the slot.

    Parameters
    ----------
    mapping:
        Mutable mapping being mutated.
    key:
        Candidate key to ensure.
    error_cls:
        Exception type raised when a scalar collision occurs.

    Returns
    -------
    dict[str, object]
        Child mapping stored at the resolved key.

    Side Effects
    ------------
    Mutates ``mapping`` by inserting a new child mapping when missing.

    Examples
    --------
    >>> target = {}
    >>> child = _ensure_child_mapping(target, 'SERVICE', error_cls=ValueError)
    >>> child == {}
    True
    >>> target
    {'service': {}}
    >>> target['service'] = 1
    >>> _ensure_child_mapping(target, 'SERVICE', error_cls=ValueError)
    Traceback (most recent call last):
    ...
    ValueError: Cannot override scalar with mapping for key SERVICE
    """

    resolved = _resolve_key(mapping, key)
    if resolved not in mapping:
        mapping[resolved] = dict[str, object]()
    child = mapping[resolved]
    if not isinstance(child, dict):
        raise error_cls(f"Cannot override scalar with mapping for key {key}")
    typed_child = cast(dict[str, object], child)
    mapping[resolved] = typed_child
    return typed_child


def _coerce(value: str) -> object:
    """Coerce textual environment values to Python primitives where possible.

    Why
    ----
    Convert human-friendly strings (``true``, ``5``, ``3.14``) into their Python
    equivalents before merging.

    What
    ----
    Applies boolean, null, integer, and float heuristics in sequence, returning
    the original string when none match.

    Returns
    -------
    object
        Parsed primitive or original string when coercion is not possible.

    Examples
    --------
    >>> _coerce('true'), _coerce('10'), _coerce('3.5'), _coerce('hello'), _coerce('null')
    (True, 10, 3.5, 'hello', None)
    """

    lowered = value.lower()
    if _looks_like_bool(lowered):
        return lowered == "true"
    if _looks_like_null(lowered):
        return None
    if _looks_like_int(value):
        return int(value)
    return _maybe_float(value)


def _looks_like_bool(value: str) -> bool:
    """Return ``True`` when *value* spells a boolean literal.

    Why
    ----
    Support `_coerce` in recognising booleans without repeated literal sets.

    Parameters
    ----------
    value:
        Lower-cased string to inspect.

    Returns
    -------
    bool
        ``True`` when the value is ``"true"`` or ``"false"``.

    Examples
    --------
    >>> _looks_like_bool('true'), _looks_like_bool('false'), _looks_like_bool('maybe')
    (True, True, False)
    """

    return value in {"true", "false"}


def _looks_like_null(value: str) -> bool:
    """Return ``True`` when *value* represents a null literal.

    Why
    ----
    Allow `_coerce` to map textual null representations to ``None``.

    Parameters
    ----------
    value:
        Lower-cased string to inspect.

    Returns
    -------
    bool
        ``True`` when the value is ``"null"`` or ``"none"``.

    Examples
    --------
    >>> _looks_like_null('null'), _looks_like_null('none'), _looks_like_null('nil')
    (True, True, False)
    """

    return value in {"null", "none"}


def _looks_like_int(value: str) -> bool:
    """Return ``True`` when *value* can be parsed as an integer.

    Why
    ----
    Let `_coerce` distinguish integers before attempting float conversion.

    Parameters
    ----------
    value:
        String to inspect (not yet normalised).

    Returns
    -------
    bool
        ``True`` when the value represents a base-10 integer literal.

    Examples
    --------
    >>> _looks_like_int('42'), _looks_like_int('-7'), _looks_like_int('3.14')
    (True, True, False)
    """

    if value.startswith("-"):
        return value[1:].isdigit()
    return value.isdigit()


def _maybe_float(value: str) -> object:
    """Return a float when *value* looks numeric; otherwise return the original string.

    Why
    ----
    Provide a final numeric coercion step after integer detection fails.

    Parameters
    ----------
    value:
        String candidate for float conversion.

    Returns
    -------
    object
        Float value or the original string when conversion fails.

    Examples
    --------
    >>> _maybe_float('2.5'), _maybe_float('not-a-number')
    (2.5, 'not-a-number')
    """

    try:
        return float(value)
    except ValueError:
        return value
