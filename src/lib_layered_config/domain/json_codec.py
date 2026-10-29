"""JSON with orjson where it can run, and stdlib json where it cannot - with the same answers.

orjson ships no free-threaded build: importing a build without free-threading support would turn
the GIL back on, and from Python 3.14 orjson is an optional extra. On a free-threaded interpreter,
or wherever orjson is not installed, every JSON view and every JSON document is handled by the
standard library instead.

The stdlib codec reproduces orjson's behaviour where the two differ by default, so a configuration
loads, is refused, and is written the same way on every interpreter. Measured differences it closes:

- Reading: stdlib json accepts ``NaN``/``Infinity``, ``1e400`` (infinity), a lone surrogate escape
  and nesting deeper than orjson's 1024 levels, and reads an integer outside ``-2**63 .. 2**64-1``
  as an exact int where orjson reads a float. Each now answers as orjson does; a too-deep document
  is refused at orjson's position even when a syntax error follows.
- Writing: orjson writes NaN and infinity as ``null``; datetimes, dates and times as ISO text; a
  UUID as its string and an Enum as its value; and refuses an integer outside the range above, a
  non-string key, a lone surrogate, a type it does not know, and nesting deeper than 254 levels.
  So does the stdlib codec.

Differences that remain:

- A small float is spelled differently, valid JSON either way and the same value when read back:
  stdlib json writes ``1e-07`` and ``1e-05`` where orjson writes ``1e-7`` and ``0.00001``.
- A refusal from the stdlib parse hooks (``NaN``, ``Infinity``, ``1e400``, a lone surrogate) names
  no position, and some syntax-error columns and messages differ by a character.
- A document refused for two reasons can name a different one on each codec, while both refuse it:
  nested past 1024 levels and holding ``NaN``, ``Infinity`` or ``1e400``, the stdlib codec names
  the value even when the depth comes first; holding a lone surrogate before the deep part, it
  names the depth. orjson reports an unclosed document 1026 to about 1100 levels deep as a memory
  error rather than as too deep.
- On Python 3.10 and 3.11 the stdlib parser stops at Python's recursion limit (1000) instead of
  1024 levels; orjson is a required dependency there, so the stdlib codec does not run.
- Values only Python code can supply (tuples, a ``time`` with ``tzinfo``, a ``str`` subclass as a
  key, dataclasses) are written by one codec and refused by the other.

Contents:
    - ``JSON_INT_MIN`` / ``JSON_INT_MAX``: the integer range a JSON view writes.
    - ``JsonCodec`` / ``OrjsonCodec`` / ``StdlibCodec``: the two backends behind one protocol.
    - ``JsonLoadError``: a refused document, with its position and whether it nests too deep.
    - ``CODEC`` / ``dumps`` / ``loads``: the codec this interpreter uses, chosen once at import.
"""

from __future__ import annotations

import datetime as dt
import enum
import importlib
import json
import math
import re
import sysconfig
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Protocol, cast

from .source_position import SourcePosition

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from types import ModuleType

__all__ = [
    "CODEC",
    "CONFIG_MAX_DEPTH",
    "JSON_ENCODE_MAX_DEPTH",
    "JSON_INT_MAX",
    "JSON_INT_MIN",
    "JSON_MAX_DEPTH",
    "JsonCodec",
    "JsonLoadError",
    "OrjsonCodec",
    "StdlibCodec",
    "dumps",
    "duplicate_keys",
    "loads",
    "nesting_depth",
    "select_codec",
]

#: The lowest integer a JSON view writes. orjson refuses anything outside ``-2**63 .. 2**64-1``,
#: so a value beyond it either stays text (environment, .env) or refuses its file (TOML, YAML).
JSON_INT_MIN: Final[int] = -(2**63)

#: The highest integer a JSON view writes; see :data:`JSON_INT_MIN`.
JSON_INT_MAX: Final[int] = 2**64 - 1

#: The deepest nesting a JSON document may have when read; orjson refuses level 1025.
JSON_MAX_DEPTH: Final[int] = 1024

#: The deepest nesting a value may have when written; orjson refuses level 255.
JSON_ENCODE_MAX_DEPTH: Final[int] = 254

#: The deepest a config may nest, counting its top-level table as level 1. ``read_config_json``
#: writes the config one level down, inside ``{"config": ..., "provenance": ...}``, so one level
#: of :data:`JSON_ENCODE_MAX_DEPTH` is spent before the config starts. A deeper value either stays
#: text (environment, .env) or refuses its file (JSON, YAML), as an out-of-range integer does.
CONFIG_MAX_DEPTH: Final[int] = JSON_ENCODE_MAX_DEPTH - 1

#: The longest integer text read as an int; longer ones are past the 64-bit range anyway, and
#: keeping them away from ``int()`` keeps them away from Python's 4300-digit conversion limit.
_MAX_INT_TEXT: Final[int] = 20

_ORJSON_TOO_DEEP: Final[str] = "depth limit exceeded"

#: The characters that open, close or quote JSON structure; the depth scan skips everything else.
_JSON_STRUCTURE: Final[re.Pattern[str]] = re.compile(r'[\[\]{}"\\]')


class JsonLoadError(ValueError):
    """A JSON document was refused.

    Attributes:
        position: The 1-based line and column the parser stopped at, or ``None`` when unknown.
        too_deep: The document nests deeper than :data:`JSON_MAX_DEPTH`; it may be well formed.
    """

    def __init__(self, message: str, *, position: SourcePosition | None = None, too_deep: bool = False) -> None:
        """Record *message* and what is known about where and why the document was refused."""
        super().__init__(message)
        self.position = position
        self.too_deep = too_deep


class JsonCodec(Protocol):
    """Read and write JSON text."""

    def dumps(self, value: object, *, indent: bool = False) -> str:
        """Return *value* as JSON: compact, or indented by two spaces.

        Raises:
            TypeError: For a value orjson would not write.
        """
        ...

    def loads(self, text: str) -> object:
        """Return the value *text* holds.

        Raises:
            JsonLoadError: For a document orjson would refuse.
        """
        ...


class _OrjsonModule(Protocol):
    """The part of the ``orjson`` module the codec uses."""

    OPT_INDENT_2: int

    def dumps(self, obj: object, /, *, option: int | None = None) -> bytes: ...

    def loads(self, obj: str, /) -> object: ...


class OrjsonCodec:
    """Read and write with orjson, the fast path on every build that can run it."""

    def __init__(self, orjson: ModuleType) -> None:
        """Bind the codec to the imported ``orjson`` module."""
        self._orjson = cast("_OrjsonModule", orjson)

    def dumps(self, value: object, *, indent: bool = False) -> str:
        """Return *value* as JSON text (see :class:`JsonCodec`)."""
        return self._orjson.dumps(value, option=self._orjson.OPT_INDENT_2 if indent else 0).decode()

    def loads(self, text: str) -> object:
        """Return the value *text* holds (see :class:`JsonCodec`)."""
        try:
            return self._orjson.loads(text)
        except json.JSONDecodeError as error:  # orjson.JSONDecodeError subclasses it
            raise JsonLoadError(
                str(error),
                position=SourcePosition(error.lineno, error.colno),
                too_deep=str(error).startswith(_ORJSON_TOO_DEEP),
            ) from error


class StdlibCodec:
    """Read and write with stdlib json, answering as orjson does.

    Examples:
        >>> StdlibCodec().dumps({"b": float("nan"), "a": 1})
        '{"b":null,"a":1}'
        >>> StdlibCodec().loads("18446744073709551616")
        1.8446744073709552e+19
    """

    def dumps(self, value: object, *, indent: bool = False) -> str:
        """Return *value* as JSON text (see :class:`JsonCodec`)."""
        return json.dumps(
            _orjson_shape(value, depth=0),
            ensure_ascii=False,
            indent=2 if indent else None,
            separators=None if indent else (",", ":"),
        )

    def loads(self, text: str) -> object:
        """Return the value *text* holds (see :class:`JsonCodec`).

        Depth is judged by a scan of the text, not by the parse: orjson stops at the first
        bracket past :data:`JSON_MAX_DEPTH`, so a too-deep document is too deep even when a
        syntax error follows, and the 3.10/3.11 parser hits Python's recursion limit first.
        """
        try:
            value: object = json.loads(
                text, parse_int=_orjson_int, parse_float=_finite_float, parse_constant=_refuse_constant
            )
        except json.JSONDecodeError as error:
            _refuse_too_deep(text, end=error.pos)
            raise JsonLoadError(str(error), position=SourcePosition(error.lineno, error.colno)) from error
        except RecursionError as error:
            _refuse_too_deep(text, end=len(text))
            raise JsonLoadError("the document nests too deep", too_deep=True) from error
        except ValueError as error:  # raised by the parse hooks below
            raise JsonLoadError(str(error)) from error
        _refuse_too_deep(text, end=len(text))
        _refuse_lone_surrogates(value)
        return value


def _orjson_int(text: str) -> int | float:
    """Read an integer literal the way orjson does: an int inside the 64-bit range, else a float.

    Examples:
        >>> _orjson_int("18446744073709551615"), _orjson_int("18446744073709551616")
        (18446744073709551615, 1.8446744073709552e+19)
    """
    if len(text) > _MAX_INT_TEXT:
        return _finite_float(text)
    number = int(text)
    return number if JSON_INT_MIN <= number <= JSON_INT_MAX else float(text)


def _finite_float(text: str) -> float:
    """Read a number literal as a float, refusing one too large to be finite, as orjson does.

    Examples:
        >>> _finite_float("1.5")
        1.5
        >>> _finite_float("1e400")
        Traceback (most recent call last):
        ...
        ValueError: number is infinity when parsed as double: 1e400
    """
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"number is infinity when parsed as double: {text[:32]}")
    return number


def _refuse_constant(name: str) -> object:
    """Refuse ``NaN``, ``Infinity`` and ``-Infinity``, which are not JSON and which orjson refuses."""
    raise ValueError(f"{name} is not a JSON value")


def _refuse_too_deep(text: str, *, end: int) -> None:
    """Refuse *text* when a bracket before *end* opens a level deeper than :data:`JSON_MAX_DEPTH`.

    Scans the text rather than the parsed value, so the verdict and position match orjson's,
    which stops at that bracket: a syntax error after it, or a parser that gives up earlier, does
    not change them. Brackets inside strings, escaped quotes included, are not counted.

    Raises:
        JsonLoadError: At orjson's position, one column past the offending bracket.

    Examples:
        >>> _refuse_too_deep('["[[["]', end=7)
        >>> _refuse_too_deep("[" * 1025, end=1025)
        Traceback (most recent call last):
        lib_layered_config.domain.json_codec.JsonLoadError: the document nests deeper than 1024 levels
    """
    depth = 0
    in_string = False
    escaped_index = -1
    for match in _JSON_STRUCTURE.finditer(text, 0, end):
        index = match.start()
        char = match.group()
        if index == escaped_index:
            continue
        if in_string:
            if char == "\\":
                escaped_index = index + 1
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > JSON_MAX_DEPTH:
                raise JsonLoadError(
                    f"the document nests deeper than {JSON_MAX_DEPTH} levels",
                    position=_orjson_position(text, index),
                    too_deep=True,
                )
        elif char in "]}":
            depth -= 1


def _orjson_position(text: str, index: int) -> SourcePosition:
    """Return the line and column orjson reports for a depth refusal at *index*.

    Examples:
        >>> _orjson_position("ab\\ncd[", 5)
        SourcePosition(line=2, column=4)
    """
    line_start = text.rfind("\n", 0, index) + 1
    return SourcePosition(text.count("\n", 0, index) + 1, index - line_start + 2)


def _refuse_lone_surrogates(value: object) -> None:
    """Refuse a parsed document holding text with a lone surrogate, as orjson does.

    Walks with an explicit stack: the document is as deep as the parser allowed, and a recursive
    walk would hit Python's recursion limit first.

    Raises:
        JsonLoadError: When a key or value holds one.
    """
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            _refuse_lone_surrogate(node)
        elif isinstance(node, dict):
            mapping = cast("dict[str, object]", node)
            stack.extend(mapping)
            stack.extend(mapping.values())
        elif isinstance(node, list):
            stack.extend(cast("list[object]", node))


def _refuse_lone_surrogate(text: str) -> None:
    """Refuse text holding an unpaired surrogate (``\\ud800``), which is no character UTF-8 can carry."""
    if text.isascii():
        return
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise JsonLoadError("the document holds a lone surrogate escape") from error


def _orjson_shape(value: object, *, depth: int) -> object:
    """Return *value* as stdlib json should write it to match orjson, refusing what orjson refuses.

    Raises:
        TypeError: For an integer outside the 64-bit range, a non-string key, an unknown type, or
            nesting deeper than :data:`JSON_ENCODE_MAX_DEPTH`.
    """
    if isinstance(value, (dict, list, tuple)):
        return _orjson_container(cast("dict[object, object] | list[object] | tuple[object, ...]", value), depth=depth)
    return _orjson_scalar(value)


def _orjson_container(
    value: dict[object, object] | list[object] | tuple[object, ...], *, depth: int
) -> dict[str, object] | list[object]:
    """Shape a container one level down (see :func:`_orjson_shape`)."""
    if depth >= JSON_ENCODE_MAX_DEPTH:
        raise TypeError("Recursion limit reached")
    if not isinstance(value, dict):
        return [_orjson_shape(item, depth=depth + 1) for item in value]
    shaped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("Dict key must be str")
        shaped[_utf8_text(key)] = _orjson_shape(item, depth=depth + 1)
    return shaped


def _utf8_text(text: str) -> str:
    """Return *text* when it can be written as UTF-8, as orjson requires.

    A lone surrogate - what an undecodable environment byte becomes under ``surrogateescape`` -
    has no UTF-8 form; orjson refuses it, while stdlib json with ``ensure_ascii=False`` would write
    it into text no UTF-8 reader accepts.

    Raises:
        TypeError: When *text* holds a lone surrogate.

    Examples:
        >>> _utf8_text("caf" + chr(0xE9)) == "caf" + chr(0xE9)
        True
        >>> _utf8_text("caf" + chr(0xDCE9))
        Traceback (most recent call last):
        TypeError: str is not valid UTF-8: surrogates not allowed
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise TypeError("str is not valid UTF-8: surrogates not allowed") from error
    return text


def _orjson_scalar(value: object) -> object:
    """Shape a scalar the way orjson writes it (see :func:`_orjson_shape`)."""
    if isinstance(value, (str, uuid.UUID)):
        # A str subclass (a str-valued Enum member) keeps its own text; a UUID becomes its string.
        return _utf8_text(value if isinstance(value, str) else str(value))
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not JSON_INT_MIN <= value <= JSON_INT_MAX:
            raise TypeError("Integer exceeds 64-bit range")
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return _orjson_scalar(cast("object", value.value))
    raise TypeError(f"Type is not JSON serializable: {type(value).__name__}")


def _import_orjson() -> ModuleType | None:
    # By name, not an import statement: orjson is absent from every 3.14+ environment of the dev
    # install (no marker tells 3.14t from 3.14), and a static import would leave the type checker
    # unable to resolve the module there.
    try:
        return importlib.import_module("orjson")
    except ImportError:
        return None


def select_codec(*, free_threaded: bool, import_orjson: Callable[[], ModuleType | None]) -> JsonCodec:
    """Return the orjson codec when it can run here, else the stdlib codec.

    Args:
        free_threaded: Whether the interpreter is a free-threaded build. orjson is never imported
            there: it has no free-threaded build, and importing one would re-enable the GIL.
        import_orjson: Returns the ``orjson`` module, or ``None`` when it is not installed.

    Examples:
        >>> isinstance(select_codec(free_threaded=True, import_orjson=lambda: None), StdlibCodec)
        True
    """
    if free_threaded:
        return StdlibCodec()
    orjson = import_orjson()
    return StdlibCodec() if orjson is None else OrjsonCodec(orjson)


#: The codec this interpreter uses, chosen once at import.
CODEC: Final[JsonCodec] = select_codec(
    free_threaded=bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    import_orjson=_import_orjson,
)


def dumps(value: object, *, indent: bool = False) -> str:
    """Write *value* with this interpreter's codec (see :class:`JsonCodec`).

    Examples:
        >>> dumps({"a": [1.5, None]})
        '{"a":[1.5,null]}'
    """
    return CODEC.dumps(value, indent=indent)


def loads(text: str) -> object:
    """Read *text* with this interpreter's codec (see :class:`JsonCodec`).

    Examples:
        >>> loads('{"a": [1, 2]}')
        {'a': [1, 2]}
    """
    return CODEC.loads(text)


class _ObjectPairs(list[tuple[str, object]]):
    """One JSON object as its pairs in file order, so a repeated key is still there to see."""


def duplicate_keys(text: str) -> list[str]:
    """Return the dotted position of every key *text* repeats within one object, sorted.

    orjson and stdlib json both keep the last value of a repeated key without a word, so a parse
    that keeps every pair is the only place the repeat can be seen. *text* must already have
    loaded through a codec: that parse has refused what this one would trip on (bad syntax, a
    constant, a nesting past :data:`CONFIG_MAX_DEPTH`).

    Examples:
        >>> duplicate_keys('{"a": 1, "b": {"c": 1, "c": 2}, "a": 3, "d": [{"e": 1, "e": 2}]}')
        ['a', 'b.c', 'd.0.e']
        >>> duplicate_keys('{"a": {"x": 1}, "b": {"x": 2}}')
        []
    """
    root: object = json.loads(text, object_pairs_hook=_ObjectPairs, parse_int=_orjson_int)
    found: list[str] = []
    pending: list[tuple[object, str]] = [(root, "")]
    while pending:
        node, position = pending.pop()
        if isinstance(node, _ObjectPairs):
            seen: set[str] = set()
            for key, value in node:
                child = f"{position}.{key}" if position else key
                if key in seen:
                    found.append(child)
                seen.add(key)
                pending.append((value, child))
        elif isinstance(node, list):
            items = cast("list[object]", node)
            pending.extend(
                (item, f"{position}.{index}" if position else str(index)) for index, item in enumerate(items)
            )
    return sorted(set(found))


def nesting_depth(value: object) -> int:
    """Return how many mappings and lists *value* nests, itself included; a scalar is 0.

    Counted with an explicit stack: a value read from JSON may nest 1024 levels, past Python's
    default recursion limit of 1000.

    Examples:
        >>> nesting_depth(1), nesting_depth([]), nesting_depth({"a": [[1], 2]})
        (0, 1, 3)
    """
    deepest = 0
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, Mapping):
            children: Iterable[object] = cast("Mapping[object, object]", node).values()
        elif isinstance(node, (list, tuple)):
            children = cast("Iterable[object]", node)
        else:
            continue
        deepest = max(deepest, depth)
        pending.extend((child, depth + 1) for child in children)
    return deepest
