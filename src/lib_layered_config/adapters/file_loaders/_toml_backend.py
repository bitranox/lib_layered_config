"""TOML parsing with rtoml where it can run, and stdlib tomllib where it cannot - with the same answers.

rtoml ships no free-threaded build: importing a build without free-threading support would turn the
GIL back on, and from Python 3.14 rtoml is an optional extra. On a free-threaded interpreter, or
wherever rtoml is not installed, TOML files are parsed with :mod:`tomllib` (Python 3.11+). Below
3.14 rtoml is a required dependency, so Python 3.10, which has no tomllib, always has rtoml.

Measured differences the stdlib parser closes, so a file loads or is refused the same way everywhere:

- rtoml refuses nesting past 80 levels of syntax; tomllib nests until Python's recursion limit.
  The two count differently (a dotted key at rtoml's limit is 80 levels deep as data, an array of
  tables 82), so no single bound matches rtoml exactly: the stdlib parser refuses a document more
  than :data:`TOML_MAX_DEPTH` levels deep, the smallest bound that never refuses a document rtoml
  accepts. Within two levels of the limit the stdlib parser therefore accepts slightly more.
- rtoml refuses an integer past 128 bits, tomllib reads any width. The file loader refuses every
  integer outside the JSON range after either parser, so both end in the same refusal - except a
  literal past Python's 4300-digit conversion limit, which both refuse as invalid TOML.

Contents:
    - ``TomlParser`` / ``RtomlParser`` / ``StdlibTomlParser``: the two backends behind one protocol.
    - ``TomlLoadError``: a refused document, with its position and whether it nests too deep.
    - ``PARSER``: the parser this interpreter uses, chosen once at import.
"""

from __future__ import annotations

import importlib
import re
import sysconfig
from typing import TYPE_CHECKING, Final, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

__all__ = [
    "PARSER",
    "TOML_MAX_DEPTH",
    "RtomlParser",
    "StdlibTomlParser",
    "TomlLoadError",
    "TomlParser",
    "select_parser",
]

#: The deepest nesting, counted as data levels with the document itself as level 1, the stdlib
#: parser accepts. rtoml's 80-level limit reaches 82 data levels for an array of tables.
TOML_MAX_DEPTH: Final[int] = 82

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
        position: The 1-based (line, column) the parser stopped at, or ``None`` when unknown.
        too_deep: The document nests deeper than the parser allows; it may be well formed.
    """

    def __init__(self, message: str, *, position: tuple[int, int] | None = None, too_deep: bool = False) -> None:
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


class _TomllibModule(Protocol):
    """The part of the ``tomllib`` module the parser uses."""

    TOMLDecodeError: type[ValueError]

    def loads(self, s: str, /) -> dict[str, object]: ...


def _rtoml_position(message: str) -> tuple[int, int] | None:
    """Return the 1-based line and column rtoml reports, or None.

    Examples:
        >>> _rtoml_position("expected an equals, found eof at line 1 column 4")
        (1, 4)
        >>> _rtoml_position("TOML parse error at line 3, column 7")
        (3, 7)
        >>> _rtoml_position("boom") is None
        True
    """
    found = _RTOML_POSITION.search(message)
    return (int(found.group(1)), int(found.group(2))) if found else None


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


class StdlibTomlParser:
    """Parse with tomllib, answering as rtoml does."""

    def __init__(self, tomllib: ModuleType) -> None:
        """Bind the parser to the imported ``tomllib`` module."""
        self._tomllib = cast("_TomllibModule", tomllib)

    def loads(self, text: str) -> dict[str, object]:
        """Return the table *text* holds (see :class:`TomlParser`)."""
        try:
            table = self._tomllib.loads(text)
        except self._tomllib.TOMLDecodeError as error:
            raise TomlLoadError(str(error), position=_tomllib_position(error)) from error
        except RecursionError as error:
            raise TomlLoadError("the document nests too deep", too_deep=True) from error
        except ValueError as error:  # an integer literal past Python's 4300-digit conversion limit
            raise TomlLoadError(str(error)) from error
        if _deeper_than(table, TOML_MAX_DEPTH):
            raise TomlLoadError(f"the document nests deeper than {TOML_MAX_DEPTH} levels", too_deep=True)
        return table


def _tomllib_position(error: ValueError) -> tuple[int, int] | None:
    """Return the 1-based line and column a ``TOMLDecodeError`` reports, or None.

    Python 3.14 carries them as attributes; earlier versions only in the message.

    Examples:
        >>> _tomllib_position(ValueError("Invalid value (at line 3, column 5)"))
        (3, 5)
        >>> _tomllib_position(ValueError("Invalid value (at end of document)")) is None
        True
    """
    line: object = getattr(error, "lineno", None)
    column: object = getattr(error, "colno", None)
    if isinstance(line, int) and isinstance(column, int):
        return line, column
    found = _TOMLLIB_POSITION.search(str(error))
    return (int(found.group(1)), int(found.group(2))) if found else None


def _deeper_than(table: dict[str, object], limit: int) -> bool:
    """Return whether *table* nests more than *limit* levels, counting itself as level 1.

    Walks with an explicit stack: the table is as deep as Python's recursion limit let the parser
    go, so a recursive walk could fail where the parser did not.

    Examples:
        >>> _deeper_than({"a": [[1]]}, 3), _deeper_than({"a": [[1]]}, 2)
        (False, True)
    """
    stack: list[tuple[object, int]] = [(table, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children: list[object] = list(cast("dict[str, object]", node).values())
        elif isinstance(node, list):
            children = cast("list[object]", node)
        else:
            continue
        if depth > limit:
            return True
        stack.extend((child, depth + 1) for child in children)
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


def _import_tomllib() -> ModuleType | None:
    return _import_module("tomllib")


def select_parser(
    *,
    free_threaded: bool,
    import_rtoml: Callable[[], ModuleType | None],
    import_tomllib: Callable[[], ModuleType | None],
) -> TomlParser:
    """Return the rtoml parser when it can run here, else the tomllib one.

    Args:
        free_threaded: Whether the interpreter is a free-threaded build. rtoml is never imported
            there: it has no free-threaded build, and importing one would re-enable the GIL.
        import_rtoml: Returns the ``rtoml`` module, or ``None`` when it is not installed.
        import_tomllib: Returns the ``tomllib`` module, or ``None`` before Python 3.11.

    Raises:
        ImportError: When neither can be imported, which only a Python 3.10 without rtoml reaches.
    """
    rtoml = None if free_threaded else import_rtoml()
    if rtoml is not None:
        return RtomlParser(rtoml)
    tomllib = import_tomllib()
    if tomllib is None:
        raise ImportError("lib_layered_config needs rtoml on Python 3.10: pip install rtoml")
    return StdlibTomlParser(tomllib)


#: The parser this interpreter uses, chosen once at import.
PARSER: Final[TomlParser] = select_parser(
    free_threaded=bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    import_rtoml=_import_rtoml,
    import_tomllib=_import_tomllib,
)
