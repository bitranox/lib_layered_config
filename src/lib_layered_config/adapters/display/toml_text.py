"""TOML text for a configuration value, key or dotted key path.

Both renderers that print a configuration as TOML-style text - ``display_config`` and the
``read`` command - write keys, table headers and values through these functions, so a key that
holds a dot, a space or a quote, and a string that holds a quote or a control character, print
the same way in both and read back as the TOML they show.
"""

from __future__ import annotations

import datetime
import math
import re
from collections.abc import Mapping, Set
from typing import TypeGuard

import orjson

__all__ = ["is_array", "is_table", "toml_key", "toml_path", "toml_value"]

# A key TOML can write without quotes; any other key is shown as a quoted string.
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
# C1 controls are legal in a TOML string but a terminal acts on them (U+009B is CSI).
_C1_CONTROL = re.compile("[\u0080-\u009f]")
_UTC_SUFFIX = "+00:00"


def is_table(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def is_array(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _is_set(value: object) -> TypeGuard[Set[object]]:
    return isinstance(value, (set, frozenset))


def toml_key(key: str) -> str:
    """Return *key* as TOML writes it: bare when it can be, quoted otherwise.

    Examples:
        >>> toml_key("db_host"), toml_key("a b"), toml_key("")
        ('db_host', '"a b"', '""')
    """
    return key if _BARE_KEY.fullmatch(key) else _toml_string(key)


def toml_path(path: tuple[str, ...]) -> str:
    """Return a key path the way TOML writes a dotted key."""
    return ".".join(toml_key(part) for part in path)


def toml_value(value: object) -> str:
    """Return *value* in TOML inline syntax; ``None``, which TOML cannot hold, shows as ``null``.

    Examples:
        >>> toml_value([{"n": 1}, None, "x"])
        '[{n = 1}, null, "x"]'
    """
    if is_table(value):
        return "{" + ", ".join(f"{toml_key(k)} = {toml_value(v)}" for k, v in value.items()) + "}"
    if is_array(value):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if _is_set(value):
        # A set has no order; sorting keeps the same configuration printing the same way.
        return "[" + ", ".join(sorted(toml_value(item) for item in value)) + "]"
    return _toml_scalar(value)


def _toml_scalar(value: object) -> str:
    """Return a scalar in TOML syntax (``null`` for ``None``)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, float) and not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    if isinstance(value, (datetime.date, datetime.time)):
        return _toml_datetime(value)
    return str(value)


def _toml_string(text: str) -> str:
    r"""Return *text* as a TOML basic string, escaping quotes and every control character.

    Examples:
        >>> _toml_string('say "hi"\x1b')
        '"say \\"hi\\"\\u001b"'
    """
    # A JSON string is a TOML basic string, except that TOML also forbids a raw DEL.
    escaped = orjson.dumps(text).decode().replace("\x7f", "\\u007f")
    return _C1_CONTROL.sub(lambda match: f"\\u{ord(match.group()):04x}", escaped)


def _toml_datetime(value: datetime.date | datetime.time) -> str:
    """Return *value* in ISO form, writing a UTC offset as ``Z`` the way TOML writers do."""
    text = value.isoformat()
    utc = isinstance(value, (datetime.datetime, datetime.time)) and value.utcoffset() == datetime.timedelta(0)
    return text[: -len(_UTC_SUFFIX)] + "Z" if utc and text.endswith(_UTC_SUFFIX) else text
