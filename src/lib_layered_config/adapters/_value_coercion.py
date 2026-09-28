"""Value rules shared by the environment and dotenv layers.

Contents:
    - ``parse_json_container``: a value that opens like a JSON array or object is parsed as one.
    - ``parse_number``: a value becomes an int or float only when the number reads back as the
      same text, so leading zeros, signs, separators and non-ASCII digits are never lost.
"""

from __future__ import annotations

import math
import re
from typing import Final

import orjson

__all__ = ["parse_json_container", "parse_number"]

_JSON_CONTAINER_PREFIXES: Final[tuple[str, ...]] = ("[", "{")
#: Exactly the texts for which ``str(int(v)) == v``: no leading zero, no "+", no "-0", ASCII digits
#: only. Nineteen digits at most keeps every value far below Python's 4300-digit int() limit.
_INT_TEXT: Final[re.Pattern[str]] = re.compile(r"0|-?[1-9][0-9]{0,18}")
#: Longer than any float ``str()`` prints; keeps a hostile value away from float().
_MAX_FLOAT_TEXT: Final[int] = 32


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
