"""The stdlib JSON codec answers like the orjson one, so a configuration behaves the same everywhere.

orjson has no free-threaded build, and from Python 3.14 it is an optional extra, so many interpreters
run the stdlib codec. Each test runs against every codec this interpreter has: the stdlib one
always, the orjson one where orjson is installed (every Python below 3.14 in this repo's dev install).
The expectations are orjson's behaviour, measured; the stdlib codec has to reproduce it.
"""

from __future__ import annotations

import datetime
import enum
import importlib.util
import json
import sys
import uuid
from typing import TYPE_CHECKING, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.domain.json_codec import (
    JSON_ENCODE_MAX_DEPTH,
    JSON_INT_MAX,
    JSON_INT_MIN,
    JSON_MAX_DEPTH,
    JsonCodec,
    JsonLoadError,
    OrjsonCodec,
    StdlibCodec,
    select_codec,
)
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from types import ModuleType

_ORJSON_INSTALLED = importlib.util.find_spec("orjson") is not None
#: A backslash, built so no escape sequence is typed into this source.
_B = chr(92)


def _codecs() -> list[JsonCodec]:
    codecs: list[JsonCodec] = [StdlibCodec()]
    if _ORJSON_INSTALLED:
        codecs.append(OrjsonCodec(importlib.import_module("orjson")))
    return codecs


CODECS = _codecs()
_needs_orjson = pytest.mark.skipif(not _ORJSON_INSTALLED, reason="orjson is not installed on this interpreter")


def _codec_id(codec: JsonCodec) -> str:
    return type(codec).__name__


def _nested(depth: int, *, kind: str) -> object:
    value: object = 1
    for _ in range(depth):
        value = [value] if kind == "list" else {"a": value}
    return value


def _depth_and_leaf(value: object) -> tuple[int, object]:
    # Walked iteratively: `==` on a 1024-deep value recurses past the 3.10/3.11 recursion limit.
    depth = 0
    while isinstance(value, (list, dict)):
        depth += 1
        value = cast("list[object]", value)[0] if isinstance(value, list) else cast("dict[str, object]", value)["a"]
    return depth, value


def _nested_text(depth: int, *, kind: str) -> str:
    if kind == "list":
        return "[" * depth + "1" + "]" * depth
    return '{"a":' * depth + "1" + "}" * depth


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("18446744073709551615", JSON_INT_MAX),
        ("-9223372036854775808", JSON_INT_MIN),
        ("18446744073709551616", 1.8446744073709552e19),
        ("-9223372036854775809", -9.223372036854776e18),
        ("1" * 25, 1.1111111111111111e24),
        ('{"a":1,"a":2}', {"a": 2}),
        ('{"k":[1,2.5,null,true,"x"]}', {"k": [1, 2.5, None, True, "x"]}),
    ],
    ids=["uint64-max", "int64-min", "above-uint64", "below-int64", "25-digits", "duplicate-key", "mixed"],
)
def test_a_document_loads_to_the_same_value(codec: JsonCodec, text: str, expected: object) -> None:
    loaded = codec.loads(text)

    assert loaded == expected
    assert type(loaded) is type(expected)


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
@pytest.mark.parametrize(
    "text",
    [
        "NaN",
        "Infinity",
        "-Infinity",
        "[NaN]",
        "1e400",
        "1" * 5000,
        '"' + _B + 'ud800"',
        '{"' + _B + 'udc00":1}',
        '{"x": }',
        "",
    ],
    ids=[
        "nan",
        "infinity",
        "minus-infinity",
        "nan-in-list",
        "1e400",
        "5000-digits",
        "lone-high",
        "lone-key",
        "bad",
        "empty",
    ],
)
def test_a_document_orjson_refuses_is_refused(codec: JsonCodec, text: str) -> None:
    with pytest.raises(JsonLoadError) as caught:
        codec.loads(text)

    assert caught.value.too_deep is False


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
@pytest.mark.parametrize("kind", ["list", "dict"])
def test_nesting_up_to_the_limit_loads_and_one_more_is_too_deep(codec: JsonCodec, kind: str) -> None:
    if isinstance(codec, StdlibCodec) and sys.version_info < (3, 12):
        pytest.skip(
            "the 3.10/3.11 C json scanner stops at sys.getrecursionlimit() (1000); there orjson is a "
            "required dependency and no free-threaded build exists, so the stdlib codec never runs"
        )

    assert _depth_and_leaf(codec.loads(_nested_text(JSON_MAX_DEPTH, kind=kind))) == (JSON_MAX_DEPTH, 1)

    with pytest.raises(JsonLoadError) as caught:
        codec.loads(_nested_text(JSON_MAX_DEPTH + 1, kind=kind))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
@pytest.mark.parametrize(
    ("text", "position"),
    # Positions measured from orjson 3.13.0: the column is one past the bracket that goes too deep.
    [
        ("[" * 1025 + "1" + "]" * 1025, (1, 1026)),
        ("[" * 1100 + "1" + "]" * 1099, (1, 1026)),
        ('{\n "a": ' + "[" * 1024 + "1" + "]" * 1024 + "}", (2, 1031)),
        ('["[[[' + _B + '"", ' + "[" * 1024 + "1" + "]" * 1025, (1, 1035)),
    ],
    ids=["list", "later-syntax-error", "second-line", "brackets-in-a-string"],
)
def test_too_deep_is_reported_where_orjson_reports_it(codec: JsonCodec, text: str, position: tuple[int, int]) -> None:
    with pytest.raises(JsonLoadError) as caught:
        codec.loads(text)

    assert (caught.value.too_deep, caught.value.position) == (True, position)


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
def test_nesting_past_the_interpreter_recursion_limit_is_too_deep(codec: JsonCodec) -> None:
    with pytest.raises(JsonLoadError) as caught:
        codec.loads(_nested_text(200_000, kind="list"))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
def test_a_syntax_error_names_its_line_and_column(codec: JsonCodec) -> None:
    with pytest.raises(JsonLoadError) as caught:
        codec.loads('{\n  "x": }')

    assert caught.value.position == (2, 8)


class _Colour(enum.Enum):
    RED = "red"


_DUMPABLE: dict[str, object] = {
    "text": 'quote " backslash \\ newline \n tab \t nul \x00 esc \x1b del \x7f line-sep '
    + chr(0x2028)
    + " e-acute "
    + chr(0xE9),
    "bounds": [JSON_INT_MIN, JSON_INT_MAX, 0, -1],
    "floats": [1.5, -0.25, 1e22],
    "flags": [True, False, None],
    "nested": {"a": {"b": [1, {"c": "d"}]}, "empty_list": [], "empty_dict": {}},
    "tuple": (1, 2),
    "moment": datetime.datetime(2026, 10, 29, 7, 32, 5, 123456, tzinfo=datetime.timezone.utc),
    "naive": datetime.datetime(2026, 10, 29, 7, 32),
    "day": datetime.date(2026, 10, 29),
    "clock": datetime.time(7, 32, 0, 123),
    "id": uuid.UUID(int=1),
    "colour": _Colour.RED,
}


@os_agnostic
@_needs_orjson
@pytest.mark.parametrize("indent", [False, True], ids=["compact", "indented"])
def test_both_codecs_write_the_same_text(indent: bool) -> None:
    orjson_codec = OrjsonCodec(importlib.import_module("orjson"))

    assert StdlibCodec().dumps(_DUMPABLE, indent=indent) == orjson_codec.dumps(_DUMPABLE, indent=indent)


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
def test_dumps_writes_nan_and_infinity_as_null(codec: JsonCodec) -> None:
    assert codec.dumps({"a": [float("nan"), float("inf"), float("-inf")]}) == '{"a":[null,null,null]}'


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
@pytest.mark.parametrize(
    "value",
    [
        {"n": JSON_INT_MAX + 1},
        {"n": JSON_INT_MIN - 1},
        {1: "int key"},
        {"s": {1, 2}},
        {"b": b"raw"},
        {"o": object()},
        # A lone surrogate is what an undecodable environment byte becomes (surrogateescape).
        {"s": "caf" + chr(0xDCE9)},
        ["ok", ["x" + chr(0xD800)]],
        {chr(0xDCFF): 1},
    ],
    ids=[
        "above-uint64",
        "below-int64",
        "int-key",
        "set",
        "bytes",
        "object",
        "surrogate",
        "nested-surrogate",
        "surrogate-key",
    ],
)
def test_dumps_refuses_what_orjson_refuses(codec: JsonCodec, value: object) -> None:
    with pytest.raises(TypeError):
        codec.dumps(value)


@os_agnostic
@pytest.mark.parametrize("codec", CODECS, ids=_codec_id)
@pytest.mark.parametrize("kind", ["list", "dict"])
def test_dumps_nests_up_to_its_limit_and_refuses_one_more(codec: JsonCodec, kind: str) -> None:
    assert codec.dumps(_nested(JSON_ENCODE_MAX_DEPTH, kind=kind)).count("1") == 1

    with pytest.raises(TypeError):
        codec.dumps(_nested(JSON_ENCODE_MAX_DEPTH + 1, kind=kind))


_TEXT = st.text(alphabet=st.characters(exclude_categories=("Cs",)))
_JSON_VALUES = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=JSON_INT_MIN, max_value=JSON_INT_MAX)
    | st.floats(allow_nan=False, allow_infinity=False)
    | _TEXT,
    lambda children: st.lists(children, max_size=4) | st.dictionaries(_TEXT, children, max_size=4),
    max_leaves=20,
)


@os_agnostic
@_needs_orjson
@given(value=_JSON_VALUES)
def test_both_codecs_load_any_document_to_the_same_value(value: object) -> None:
    text = json.dumps(value, ensure_ascii=False)

    assert StdlibCodec().loads(text) == OrjsonCodec(importlib.import_module("orjson")).loads(text)


@os_agnostic
@given(value=_JSON_VALUES)
def test_the_stdlib_codec_reads_back_what_it_writes(value: object) -> None:
    codec = StdlibCodec()

    assert codec.loads(codec.dumps(value)) == value


def _never_import() -> ModuleType | None:
    raise AssertionError("orjson must not be imported on a free-threaded interpreter")


def _absent() -> ModuleType | None:
    return None


@os_agnostic
def test_a_free_threaded_interpreter_never_imports_orjson() -> None:
    assert isinstance(select_codec(free_threaded=True, import_orjson=_never_import), StdlibCodec)


@os_agnostic
def test_without_orjson_the_stdlib_codec_is_chosen() -> None:
    assert isinstance(select_codec(free_threaded=False, import_orjson=_absent), StdlibCodec)


@os_agnostic
@_needs_orjson
def test_with_orjson_and_the_gil_the_orjson_codec_is_chosen() -> None:
    orjson = importlib.import_module("orjson")

    def _installed() -> ModuleType | None:
        return orjson

    assert isinstance(select_codec(free_threaded=False, import_orjson=_installed), OrjsonCodec)
