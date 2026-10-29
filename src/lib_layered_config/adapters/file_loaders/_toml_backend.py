"""TOML parsing with rtoml where it can run, and tomli / tomllib where it cannot - with the same answers.

rtoml ships no free-threaded build: importing a build without free-threading support would turn the
GIL back on, and from Python 3.14 rtoml is an optional extra. On a free-threaded interpreter, or
wherever rtoml is not installed, TOML files are parsed with tomli (a dependency on Python 3.14, where
:mod:`tomllib` still reads TOML 1.0) or :mod:`tomllib` (TOML 1.1 from Python 3.15). Below 3.14
rtoml is a required dependency, so Python 3.10, which has no tomllib, always has rtoml.

Measured differences the tomli parser closes, so a file loads or is refused the same way everywhere:

- rtoml refuses more than 80 levels of nesting per construct: a table header, a dotted key, and a
  value each count on their own, so a header holding a dotted key can be 160 tables deep. The parsed
  data no longer shows which construct made a level, so the tomli parser applies two bounds instead:
  tables nested past :data:`TOML_MAX_TABLE_DEPTH`, the depth the merge refuses for tables outside
  arrays on every path, and arrays nested directly in arrays past :data:`TOML_MAX_ARRAY_DEPTH`,
  rtoml's own limit. What stays apart: a single table header or inline table 81 to 100 levels deep,
  or a dotted key of 81 to 101 keys, loads with tomli and is refused by rtoml, and so does a value
  alternating arrays and inline tables past 80 levels. The other way round, the merge does not look
  inside arrays, so rtoml's path loads tables nested past 101 levels inside an array of tables
  (80 per construct), while the tomli parser counts tables through the array and refuses them.
  Counting afresh inside each array instead would let a chain of array-of-tables headers nest
  without any bound.
- rtoml accepts a leading byte order mark; tomli refuses it, so the parser skips it.
- rtoml refuses a float literal too large for a float (``1e400``); tomli reads it as infinity, so
  the parser refuses it. The ``inf`` and ``nan`` literals load on both.
- rtoml refuses an integer past 128 bits, tomli reads any width. The file loader refuses every
  integer outside the JSON range after either parser, so both end in a refusal, with different
  messages - except a literal past Python's 4300-digit conversion limit, which both refuse as
  invalid TOML.
- A too-deep or float-overflow refusal from the tomli parser names no position, where rtoml names
  one, and some syntax-error columns differ by one.

Contents:
    - ``TomlParser`` / ``RtomlParser`` / ``TomliParser``: the backends behind one protocol; the
      tomli parser runs tomli or tomllib, which share one API.
    - ``TomlLoadError``: a refused document, with its position and whether it nests too deep.
    - ``PARSER``: the parser this interpreter uses, chosen once at import.
"""

from __future__ import annotations

import importlib
import math
import re
import sys
import sysconfig
from typing import TYPE_CHECKING, Final, Protocol, cast

from ...domain.source_position import SourcePosition

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

__all__ = [
    "PARSER",
    "TOML_MAX_ARRAY_DEPTH",
    "TOML_MAX_TABLE_DEPTH",
    "RtomlParser",
    "TomlLoadError",
    "TomlParser",
    "TomliParser",
    "select_parser",
]

#: The deepest table nesting the tomli parser accepts, counting the document as level 1 and counting
#: through arrays. The merge refuses deeper tables outside arrays on every path (``application.merge``),
#: so there a file this parser refuses for its tables is one that rtoml's path refuses too, one step
#: later; inside an array the two differ (see the module docstring).
TOML_MAX_TABLE_DEPTH: Final[int] = 101

#: The most arrays nested directly in one another the tomli parser accepts: rtoml's limit for a value.
TOML_MAX_ARRAY_DEPTH: Final[int] = 80

#: A UTF-8 byte order mark as the decoder leaves it at the start of the text.
_BYTE_ORDER_MARK: Final[str] = chr(0xFEFF)

#: rtoml's message is read only for the numbers in it; "line 1 column 4" (toml 0.5) and
#: "line 1, column 4" (newer renderers, which also print a source snippet) both match.
_RTOML_POSITION: Final[re.Pattern[str]] = re.compile(r"line (\d+),? column (\d+)")

#: rtoml's two depth refusals: "cannot recurse further; max recursion depth met at ..." for an
#: array or inline table, "recursion limit" for a table header or dotted key. Fixed wording that
#: carries no file content.
_RTOML_TOO_DEEP: Final[re.Pattern[str]] = re.compile(r"recursion")

#: tomllib before 3.14 carries the position only in its message: "Invalid value (at line 3, column 5)".
_TOMLLIB_POSITION: Final[re.Pattern[str]] = re.compile(r"\(at line (\d+), column (\d+)\)")


class TomlLoadError(ValueError):
    """A TOML document was refused.

    Attributes:
        position: The 1-based line and column the parser stopped at, or ``None`` when unknown.
        too_deep: The document nests deeper than the parser allows; it may be well formed.
    """

    def __init__(self, message: str, *, position: SourcePosition | None = None, too_deep: bool = False) -> None:
        """Record *message* and what is known about where and why the document was refused."""
        super().__init__(message)
        self.position = position
        self.too_deep = too_deep


class TomlParser(Protocol):
    """Parse TOML text."""

    def loads(self, text: str) -> dict[str, object]:
        """Return the table *text* holds.

        Raises:
            TomlLoadError: For a document rtoml would refuse.
        """
        ...


class _RtomlModule(Protocol):
    """The part of the ``rtoml`` module the parser uses."""

    TomlParsingError: type[ValueError]

    def loads(self, toml: str, /) -> dict[str, object]: ...


class _TomliModule(Protocol):
    """The part of the ``tomli`` / ``tomllib`` module the parser uses."""

    TOMLDecodeError: type[ValueError]

    def loads(self, s: str, /, *, parse_float: Callable[[str], object]) -> dict[str, object]: ...


def _rtoml_position(message: str) -> SourcePosition | None:
    """Return the 1-based line and column rtoml reports, or None.

    Examples:
        >>> _rtoml_position("expected an equals, found eof at line 1 column 4")
        SourcePosition(line=1, column=4)
        >>> _rtoml_position("TOML parse error at line 3, column 7")
        SourcePosition(line=3, column=7)
        >>> _rtoml_position("boom") is None
        True
    """
    found = _RTOML_POSITION.search(message)
    return SourcePosition(int(found.group(1)), int(found.group(2))) if found else None


class RtomlParser:
    """Parse with rtoml, the fast path on every build that can run it.

    Examples:
        >>> import importlib.util
        >>> if importlib.util.find_spec("rtoml"):
        ...     print(RtomlParser(importlib.import_module("rtoml")).loads("a = 1"))
        ... else:
        ...     print({"a": 1})
        {'a': 1}
    """

    def __init__(self, rtoml: ModuleType) -> None:
        """Bind the parser to the imported ``rtoml`` module."""
        self._rtoml = cast("_RtomlModule", rtoml)

    def loads(self, text: str) -> dict[str, object]:
        """Return the table *text* holds (see :class:`TomlParser`)."""
        try:
            return self._rtoml.loads(text)
        except self._rtoml.TomlParsingError as error:
            message = str(error)
            raise TomlLoadError(
                message, position=_rtoml_position(message), too_deep=_RTOML_TOO_DEEP.search(message) is not None
            ) from error


class TomliParser:
    """Parse with tomli or tomllib, answering as rtoml does.

    Examples:
        >>> import importlib.util
        >>> name = "tomllib" if importlib.util.find_spec("tomllib") else "tomli"
        >>> TomliParser(importlib.import_module(name)).loads(chr(0xFEFF) + "a = 1")
        {'a': 1}
    """

    def __init__(self, tomli: ModuleType) -> None:
        """Bind the parser to the imported ``tomli`` or ``tomllib`` module."""
        self._tomli = cast("_TomliModule", tomli)

    def loads(self, text: str) -> dict[str, object]:
        """Return the table *text* holds (see :class:`TomlParser`)."""
        try:
            table = self._tomli.loads(text.removeprefix(_BYTE_ORDER_MARK), parse_float=_finite_float)
        except self._tomli.TOMLDecodeError as error:
            raise TomlLoadError(str(error), position=_tomllib_position(error)) from error
        except RecursionError as error:
            raise TomlLoadError("the document nests too deep", too_deep=True) from error
        except ValueError as error:  # a float past the float range, or an integer past 4300 digits
            raise TomlLoadError(str(error)) from error
        if _nests_too_deep(table):
            raise TomlLoadError(
                f"the document nests tables deeper than {TOML_MAX_TABLE_DEPTH} levels "
                f"or arrays deeper than {TOML_MAX_ARRAY_DEPTH}",
                too_deep=True,
            )
        return table


def _finite_float(text: str) -> float:
    """Read a TOML float literal, refusing one too large for a float as rtoml does.

    Examples:
        >>> _finite_float("1_000.5"), _finite_float("inf"), _finite_float("1e-400")
        (1000.5, inf, 0.0)
        >>> _finite_float("-1e400")
        Traceback (most recent call last):
        ...
        ValueError: the float -1e400 is too large
    """
    value = float(text)
    if math.isfinite(value) or text.lstrip("+-") in {"inf", "nan"}:
        return value
    raise ValueError(f"the float {text} is too large")


def _tomllib_position(error: ValueError) -> SourcePosition | None:
    """Return the 1-based line and column a ``TOMLDecodeError`` reports, or None.

    Python 3.14 carries them as attributes; earlier versions only in the message.

    Examples:
        >>> _tomllib_position(ValueError("Invalid value (at line 3, column 5)"))
        SourcePosition(line=3, column=5)
        >>> _tomllib_position(ValueError("Invalid value (at end of document)")) is None
        True
    """
    line: object = getattr(error, "lineno", None)
    column: object = getattr(error, "colno", None)
    if isinstance(line, int) and isinstance(column, int):
        return SourcePosition(line, column)
    found = _TOMLLIB_POSITION.search(str(error))
    return SourcePosition(int(found.group(1)), int(found.group(2))) if found else None


def _nests_too_deep(table: dict[str, object]) -> bool:
    """Return whether *table* nests tables or directly nested arrays past the parser's bounds.

    Tables count from the document as level 1 (:data:`TOML_MAX_TABLE_DEPTH`); arrays count only
    while each sits directly in the one before (:data:`TOML_MAX_ARRAY_DEPTH`). Walks with an
    explicit stack: the table is as deep as Python's recursion limit let the parser go, so a
    recursive walk could fail where the parser did not.

    Examples:
        >>> _nests_too_deep({"a": [[1]]})
        False
        >>> deep: dict[str, object] = {"k": 1}
        >>> for _ in range(TOML_MAX_TABLE_DEPTH):
        ...     deep = {"a": deep}
        >>> _nests_too_deep(deep)
        True
    """
    stack: list[tuple[object, int, int]] = [(table, 1, 0)]
    while stack:
        node, tables, arrays = stack.pop()
        if isinstance(node, dict):
            if tables > TOML_MAX_TABLE_DEPTH:
                return True
            stack.extend((child, tables + 1, 0) for child in cast("dict[str, object]", node).values())
        elif isinstance(node, list):
            if arrays + 1 > TOML_MAX_ARRAY_DEPTH:
                return True
            stack.extend((child, tables, arrays + 1) for child in cast("list[object]", node))
    return False


def _import_module(name: str) -> ModuleType | None:
    # By name, not an import statement: rtoml is absent from every 3.14+ environment of the dev
    # install, and tomllib from 3.10, so a static import would leave the type checker unable to
    # resolve one of them on some interpreter.
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _import_rtoml() -> ModuleType | None:
    return _import_module("rtoml")


def _import_tomli() -> ModuleType | None:
    # From Python 3.15 tomllib reads TOML 1.1 itself, and a tomli some other package installed there
    # may predate tomli 2.4.0, the first that reads TOML 1.1.
    return _import_module("tomli") if sys.version_info < (3, 15) else None


def _import_tomllib() -> ModuleType | None:
    return _import_module("tomllib")


def select_parser(
    *,
    free_threaded: bool,
    import_rtoml: Callable[[], ModuleType | None],
    import_tomli: Callable[[], ModuleType | None],
    import_tomllib: Callable[[], ModuleType | None],
) -> TomlParser:
    """Return the rtoml parser when it can run here, else tomli, else tomllib.

    Args:
        free_threaded: Whether the interpreter is a free-threaded build. rtoml is never imported
            there: it has no free-threaded build, and importing one would re-enable the GIL.
        import_rtoml: Returns the ``rtoml`` module, or ``None`` when it is not installed.
        import_tomli: Returns the ``tomli`` module, or ``None`` when it is not installed or not
            wanted (from Python 3.15 tomllib reads TOML 1.1).
        import_tomllib: Returns the ``tomllib`` module, or ``None`` before Python 3.11.

    Raises:
        ImportError: When none can be imported, which only a Python 3.10 without rtoml reaches.
    """
    rtoml = None if free_threaded else import_rtoml()
    if rtoml is not None:
        return RtomlParser(rtoml)
    tomli = import_tomli() or import_tomllib()
    if tomli is None:
        raise ImportError("lib_layered_config needs rtoml on Python 3.10: pip install rtoml")
    return TomliParser(tomli)


#: The parser this interpreter uses, chosen once at import.
PARSER: Final[TomlParser] = select_parser(
    free_threaded=bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    import_rtoml=_import_rtoml,
    import_tomli=_import_tomli,
    import_tomllib=_import_tomllib,
)
