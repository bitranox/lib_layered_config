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
from typing import TYPE_CHECKING, Final

from ...domain.errors import InvalidFormatError
from ...domain.redaction import NotSensitiveKeys
from ...observability import log_debug
from .._nested_keys import assign_nested
from .._value_coercion import coerce_value

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


__all__ = [
    "DefaultEnvLoader",
    "default_env_prefix",
]


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

    def __init__(
        self, *, environ: dict[str, str] | None = None, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE
    ) -> None:
        """Initialise the loader with a specific ``environ`` mapping for testability.

        Allow tests and callers to supply deterministic environments.

        Args:
            environ: Mapping to read from. Defaults to :data:`os.environ`.
            not_sensitive: Paths the application declared not sensitive; their ``null``/``none``
                reads as None.
        """
        self._environ = os.environ if environ is None else environ
        self._not_sensitive = not_sensitive

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
            _refuse_undecodable(normalized_prefix + raw_key, value)
            assign_nested(
                collected,
                raw_key,
                coerce_value(raw_key, value, not_sensitive=self._not_sensitive),
                error_cls=ValueError,
            )
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


def _refuse_undecodable(name: str, value: str) -> None:
    r"""Refuse a variable whose name or value has no UTF-8 form, naming it, never its value.

    POSIX hands Python each byte of an environment entry that is not UTF-8 as a lone surrogate
    (``b"a\xff"`` reads as ``"a\udcff"``), and Windows passes an unpaired UTF-16 surrogate through
    as one. Such a value loaded, then crashed every JSON view; a ``.env`` file with the same bytes
    is already refused, and this gives the environment the same rule.

    Raises:
        InvalidFormatError: When *name* or *value* holds a lone surrogate.

    Examples:
        >>> _refuse_undecodable("DEMO___KEY", "Gr\u00fc\u00dfe")
        >>> _refuse_undecodable("DEMO___KEY", "a\udcffb")
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: environment variable DEMO___KEY ... (byte offset 1)
        >>> _refuse_undecodable("DEMO___K\udcffEY", "a")
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: environment variable name DEMO___K\xffEY ...
    """
    name_offset = _first_undecodable_offset(name)
    if name_offset is not None:
        message = f"environment variable name {_escape_surrogates(name)} is not valid UTF-8 (byte offset {name_offset})"
        raise InvalidFormatError(message)
    value_offset = _first_undecodable_offset(value)
    if value_offset is not None:
        raise InvalidFormatError(f"environment variable {name} is not valid UTF-8 (byte offset {value_offset})")


def _first_undecodable_offset(text: str) -> int | None:
    r"""Return the UTF-8 byte offset of the first lone surrogate in *text*, or ``None``.

    Examples:
        >>> _first_undecodable_offset("\u00e9a\udcff"), _first_undecodable_offset("plain")
        (3, None)
    """
    for index, char in enumerate(text):
        if _SURROGATE_FIRST <= ord(char) <= _SURROGATE_LAST:
            return len(text[:index].encode("utf-8"))
    return None


def _escape_surrogates(text: str) -> str:
    r"""Return *text* with each lone surrogate written as an escape: ``\xNN`` for a byte POSIX passed
    through undecoded, ``\uXXXX`` for any other.

    Examples:
        >>> print(_escape_surrogates("K\udcffY\ud800"))
        K\xffY\ud800
    """
    return "".join(_escape_one(char) for char in text)


def _escape_one(char: str) -> str:
    code = ord(char)
    if _ESCAPED_BYTE_FIRST <= code <= _SURROGATE_LAST:
        return f"\\x{code - _SURROGATE_ESCAPE_BASE:02x}"
    if _SURROGATE_FIRST <= code <= _SURROGATE_LAST:
        return f"\\u{code:04x}"
    return char


#: The UTF-16 surrogate range; a lone one has no UTF-8 encoding.
_SURROGATE_FIRST: Final[int] = 0xD800
_SURROGATE_LAST: Final[int] = 0xDFFF
#: Python's ``surrogateescape`` error handler maps an undecodable byte B to ``U+DC00 + B`` (B >= 0x80).
_SURROGATE_ESCAPE_BASE: Final[int] = 0xDC00
_ESCAPED_BYTE_FIRST: Final[int] = 0xDC80


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
