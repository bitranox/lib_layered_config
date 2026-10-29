"""JSON encoding and decoding rules every layer shares.

Contents:
    - ``JSON_INT_MIN`` / ``JSON_INT_MAX``: the integer range a JSON view of a configuration
      can write.
"""

from __future__ import annotations

from typing import Final

__all__ = ["JSON_INT_MAX", "JSON_INT_MIN"]

#: The lowest integer a JSON view writes. orjson refuses anything outside ``-2**63 .. 2**64-1``,
#: so a value beyond it either stays text (environment, .env) or refuses its file (TOML, YAML).
JSON_INT_MIN: Final[int] = -(2**63)

#: The highest integer a JSON view writes; see :data:`JSON_INT_MIN`.
JSON_INT_MAX: Final[int] = 2**64 - 1
