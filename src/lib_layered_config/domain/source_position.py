"""Where in a configuration file a parser stopped.

Contents:
    - ``SourcePosition``: a 1-based line and column, as the TOML, JSON and YAML parsers report them.
"""

from __future__ import annotations

from typing import NamedTuple


class SourcePosition(NamedTuple):
    """A 1-based line and column in a source text.

    A ``NamedTuple``, so code that unpacks ``line, column = position`` or compares it with a plain
    tuple keeps working.

    Examples:
        >>> SourcePosition(line=3, column=7)
        SourcePosition(line=3, column=7)
        >>> SourcePosition(3, 7) == (3, 7)
        True
    """

    line: int
    column: int


__all__ = ["SourcePosition"]
