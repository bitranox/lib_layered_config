"""Read TOML in a test independently of the parser the library chose.

The library parses with rtoml or tomllib depending on the interpreter. A test that checks the
library's own output reads it back with tomllib (Python 3.11+), falling back to rtoml on Python 3.10,
where rtoml is a required dependency and tomllib does not exist.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Protocol, cast

__all__ = ["loads_toml"]


class _TomlReader(Protocol):
    def loads(self, text: str, /) -> dict[str, object]: ...


def _reader() -> _TomlReader:
    name = "tomllib" if importlib.util.find_spec("tomllib") is not None else "rtoml"
    return cast("_TomlReader", importlib.import_module(name))


def loads_toml(text: str) -> dict[str, object]:
    """Return the table *text* holds.

    Examples:
        >>> loads_toml('a = 1')
        {'a': 1}
    """
    return _reader().loads(text)
