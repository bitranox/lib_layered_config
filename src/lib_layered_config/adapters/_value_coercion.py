"""Value rules shared by the environment and dotenv layers.

Contents:
    - ``coerce_value``: the conversion both layers apply to an unquoted value - a JSON container,
      ``true``/``false``, ``null``/``none`` (kept as text for a sensitive key unless the
      application declared it not sensitive), a lossless number,
      otherwise the text unchanged.
    - ``parse_json_container``: a value that opens like a JSON array or object is parsed as one.
    - ``parse_number``: a value becomes an int or float only when the number reads back as the
      same text, so leading zeros, signs, separators and non-ASCII digits are never lost.
"""

from __future__ import annotations

import math
import re
from typing import Final

import orjson

from ..domain.redaction import NotSensitiveKeys, is_sensitive_at
from ._nested_keys import NESTED_KEY_DELIMITER

__all__ = ["coerce_value", "parse_json_container", "parse_number"]

_BOOL_TRUE: Final[str] = "true"
_BOOL_LITERALS: Final[frozenset[str]] = frozenset({_BOOL_TRUE, "false"})
_NULL_LITERALS: Final[frozenset[str]] = frozenset({"null", "none"})
_JSON_CONTAINER_PREFIXES: Final[tuple[str, ...]] = ("[", "{")
#: Exactly the texts for which ``str(int(v)) == v``: no leading zero, no "+", no "-0", ASCII digits
#: only. Nineteen digits at most keeps every value far below Python's 4300-digit int() limit.
_INT_TEXT: Final[re.Pattern[str]] = re.compile(r"0|-?[1-9][0-9]{0,18}")
#: Longer than any float ``str()`` prints; keeps a hostile value away from float().
_MAX_FLOAT_TEXT: Final[int] = 32


def coerce_value(raw_key: str, value: str, *, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE) -> object:
    """Convert an unquoted *value* the way the environment and dotenv layers read it.

    A JSON array or object is parsed, ``true``/``false`` become a bool, ``null``/``none`` become
    None, and a number becomes an int or float only when it reads back as the same text; anything
    else stays the text it is. A sensitive key (one ``redact=True`` masks) keeps ``null``/``none``
    as text: None would mean "no credential", and a consumer would then proceed without one
    instead of failing to log in. A key the application declared not sensitive reads them as None
    like any other key.

    Args:
        raw_key: Variable name with the prefix removed, segments separated by ``__``.
        value: The value as written, without surrounding quotes.
        not_sensitive: Paths the application declared not sensitive.

    Returns:
        The converted value.

    Examples:
        >>> coerce_value("SERVICE__ENABLED", "true"), coerce_value("SERVICE__RETRIES", "10")
        (True, 10)
        >>> coerce_value("SERVICE__TIMEOUT", "null") is None, coerce_value("ZIP", "007")
        (True, '007')
        >>> coerce_value("EMAIL__SMTP_PASSWORD", "none")
        'none'
        >>> declared = NotSensitiveKeys.of(["performance.max_token_bytes"])
        >>> coerce_value("PERFORMANCE__MAX_TOKEN_BYTES", "null", not_sensitive=declared) is None
        True
    """
    container = parse_json_container(value)
    if container is not None:
        return container
    lowered = value.lower()
    if lowered in _BOOL_LITERALS:
        return lowered == _BOOL_TRUE
    if lowered in _NULL_LITERALS:
        return value if _key_is_sensitive(raw_key, not_sensitive) else None
    number = parse_number(value)
    return value if number is None else number


def _key_is_sensitive(raw_key: str, not_sensitive: NotSensitiveKeys) -> bool:
    """Return whether the key *raw_key* names is masked: its leaf looks secret and nothing declared it.

    Examples:
        >>> _key_is_sensitive("EMAIL__SMTP_PASSWORD", NotSensitiveKeys.NONE)
        True
        >>> _key_is_sensitive("CREDENTIALS__TIMEOUT", NotSensitiveKeys.NONE)
        False
    """
    return is_sensitive_at(raw_key.lower().split(NESTED_KEY_DELIMITER), not_sensitive=not_sensitive)


def parse_json_container(value: str) -> list[object] | dict[str, object] | None:
    """Parse *value* as a JSON array/object when it opens like one, else return ``None``.

    Examples:
        >>> parse_json_container('[1, 2]')
        [1, 2]
        >>> parse_json_container('{"a": 1}')
        {'a': 1}
        >>> parse_json_container('plain') is None
        True
        >>> parse_json_container('[bad') is None
        True
    """
    if not value.startswith(_JSON_CONTAINER_PREFIXES):
        return None
    try:
        return orjson.loads(value)
    except orjson.JSONDecodeError:
        return None


def parse_number(value: str) -> int | float | None:
    """Return the int or float *value* spells exactly, else ``None``.

    Examples:
        >>> parse_number("5"), parse_number("-7"), parse_number("3.5")
        (5, -7, 3.5)
        >>> [parse_number(text) for text in ("007123", "1.50", "+5", "1_000", "nan", "inf")]
        [None, None, None, None, None, None]
    """
    if _INT_TEXT.fullmatch(value):
        return int(value)
    if len(value) > _MAX_FLOAT_TEXT or not value.isascii():
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    # "nan" and "inf" read back as themselves, so the round trip alone would keep them.
    if math.isfinite(number) and str(number) == value:
        return number
    return None
