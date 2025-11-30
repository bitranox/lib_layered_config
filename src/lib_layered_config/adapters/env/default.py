"""Environment variable adapter.

Purpose
-------
Translate process environment variables into nested configuration dictionaries.
It implements the port described in ``docs/systemdesign/module_reference.md``
and forms the final precedence layer in ``lib_layered_config``.

Contents
    - ``default_env_prefix``: canonical prefix builder for a slug.
    - ``DefaultEnvLoader``: orchestrates filtering, coercion, and nesting.
    - ``_coerce`` plus tiny predicate helpers that translate strings into
      Python primitives.
    - ``_normalize_prefix`` / ``_iter_namespace_entries`` / ``_collect_keys``:
      small verbs that keep the loader body declarative.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator

from .._nested_keys import assign_nested
from ...observability import log_debug


def default_env_prefix(slug: str) -> str:
    """Return the canonical environment prefix for *slug*.

    Why
    ----
    Namespacing prevents unrelated environment variables from leaking into the
    configuration payload. The triple underscore (``___``) separator clearly
    distinguishes the application prefix from section/key separators which use
    double underscores (``__``).

    Parameters
    ----------
    slug:
        Package/application slug (typically ``kebab-case``).

    Returns
    -------
    str
        Upper-case prefix with dashes converted to underscores, ending with
        triple underscore separator.

    Examples
    --------
    >>> default_env_prefix('lib-layered-config')
    'LIB_LAYERED_CONFIG___'
    """

    return slug.replace("-", "_").upper() + "___"


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
            Prefix filter (upper-case). The loader appends ``___`` if missing.

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
        ...     'DEMO___SERVICE__ENABLED': 'true',
        ...     'DEMO___SERVICE__RETRIES': '3',
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
            assign_nested(collected, raw_key, _coerce(value), error_cls=ValueError)
        log_debug("env_variables_loaded", layer="env", path=None, keys=_collect_keys(collected))
        return collected


def _normalize_prefix(prefix: str) -> str:
    """Ensure the prefix ends with triple underscore when non-empty.

    Why
    ----
    Aligns environment variable filtering semantics regardless of user input.
    The triple underscore (``___``) separator clearly distinguishes the
    application prefix from section/key separators (``__``).

    Parameters
    ----------
    prefix:
        Raw prefix string (upper-case expected but not enforced).

    Returns
    -------
    str
        Prefix guaranteed to end with ``___`` when non-empty.

    Examples
    --------
    >>> _normalize_prefix('DEMO')
    'DEMO___'
    >>> _normalize_prefix('DEMO___')
    'DEMO___'
    >>> _normalize_prefix('')
    ''
    """

    if prefix and not prefix.endswith("___"):
        return f"{prefix}___"
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
        Normalised prefix (including trailing triple underscore) to filter on.

    Returns
    -------
    Iterator[tuple[str, str]]
        Pairs whose keys share the prefix with the prefix removed.

    Examples
    --------
    >>> list(_iter_namespace_entries([('DEMO___FLAG', '1'), ('OTHER', '0')], 'DEMO___'))
    [('FLAG', '1')]
    >>> list(_iter_namespace_entries([('DEMO', '1')], 'DEMO___'))
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
