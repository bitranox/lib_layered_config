"""Environment variable adapter.

Translate process environment variables into nested configuration dictionaries.
It implements the port described in ``docs/systemdesign/module_reference.md``
and forms the final precedence layer in ``lib_layered_config``.

Contents:
    - ``default_env_prefix``: canonical prefix builder for a slug.
    - ``DefaultEnvLoader``: orchestrates filtering, coercion, and nesting.
    - ``_normalize_prefix`` / ``_iter_namespace_entries`` / ``_collect_keys``:
      small verbs that keep the loader body declarative.

Each value is converted by ``.._value_coercion.coerce_value``, the rule the dotenv layer shares.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ...observability import log_debug
from .._nested_keys import assign_nested
from .._value_coercion import coerce_value

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


def default_env_prefix(slug: str) -> str:
    """Return the canonical environment prefix for *slug*.

    Namespacing prevents unrelated environment variables from leaking into the
    configuration payload. The triple underscore (``___``) separator clearly
    distinguishes the application prefix from section/key separators which use
    double underscores (``__``).

    Args:
        slug: Package/application slug (typically ``kebab-case``).

    Returns:
        Upper-case prefix with dashes converted to underscores, ending with
        triple underscore separator.

    Examples:
        >>> default_env_prefix('lib-layered-config')
        'LIB_LAYERED_CONFIG___'
    """
    return slug.replace("-", "_").upper() + "___"


class DefaultEnvLoader:
    """Load environment variables that belong to the configuration namespace.

    Implements the :class:`lib_layered_config.application.ports.EnvLoader` port,
    translating process environment variables into merge-ready payloads.

    Filters environment entries by prefix, nests values using ``__`` separators,
    performs primitive coercion, and emits observability events.
    """

    def __init__(self, *, environ: dict[str, str] | None = None) -> None:
        """Initialise the loader with a specific ``environ`` mapping for testability.

        Allow tests and callers to supply deterministic environments.

        Args:
            environ: Mapping to read from. Defaults to :data:`os.environ`.
        """
        self._environ = os.environ if environ is None else environ

    def load(self, prefix: str) -> dict[str, object]:
        """Return a nested mapping containing variables with the supplied *prefix*.

        Environment variables should integrate with the merge pipeline using the
        same nesting semantics as `.env` files.

        Normalises the prefix, filters matching entries, coerces values, nests
        keys via :func:`assign_nested`, and logs the summarised result.

        Args:
            prefix: Prefix filter (upper-case). The loader appends ``___`` if missing.

        Returns:
            Nested mapping suitable for the merge algorithm. Keys are stored in
            lowercase to align with file-based layers.

        Side Effects:
            Emits ``env_variables_loaded`` debug events with summarised keys.

        Examples:
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
            assign_nested(collected, raw_key, coerce_value(raw_key, value), error_cls=ValueError)
        log_debug("env_variables_loaded", layer="env", path=None, keys=_collect_keys(collected))
        return collected


def _normalize_prefix(prefix: str) -> str:
    """Ensure the prefix ends with triple underscore when non-empty.

    Aligns environment variable filtering semantics regardless of user input.
    The triple underscore (``___``) separator clearly distinguishes the
    application prefix from section/key separators (``__``).

    Args:
        prefix: Raw prefix string (upper-case expected but not enforced).

    Returns:
        Prefix guaranteed to end with ``___`` when non-empty.

    Examples:
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

    Encapsulate prefix filtering so caller code stays declarative.

    Args:
        items: Iterable of environment items to examine.
        prefix: Normalised prefix (including trailing triple underscore) to filter on.

    Returns:
        Pairs whose keys share the prefix with the prefix removed.

    Examples:
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

    Provide compact telemetry context without dumping entire payloads.

    Args:
        mapping: Nested mapping produced by environment parsing.

    Returns:
        Sorted list of top-level keys.

    Examples:
        >>> _collect_keys({'service': {}, 'logging': {}})
        ['logging', 'service']
    """
    return sorted(mapping.keys())
