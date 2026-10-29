"""The stdlib-style TOML parsers answer like rtoml, so a TOML file loads or is refused the same everywhere.

rtoml has no free-threaded build, and from Python 3.14 it is an optional extra, so many interpreters
parse TOML with tomli (a dependency on Python 3.14, where ``tomllib`` still reads TOML 1.0) or the
standard library's ``tomllib`` (Python 3.11+). Each test runs against every parser this interpreter
has. rtoml counts nesting per construct (80 levels for a table header, a dotted key, or a value), a
count the parsed data cannot reproduce. The other parsers refuse tables nested deeper than the merge
accepts (:data:`TOML_MAX_TABLE_DEPTH`) and arrays nested directly in arrays past rtoml's 80
(:data:`TOML_MAX_ARRAY_DEPTH`).
"""

from __future__ import annotations

import importlib
import importlib.util
import math
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.display.toml_text import toml_value
from lib_layered_config.adapters.file_loaders._toml_backend import (
    PARSER,
    TOML_MAX_ARRAY_DEPTH,
    TOML_MAX_TABLE_DEPTH,
    RtomlParser,
    TomliParser,
    TomlLoadError,
    TomlParser,
    select_parser,
)
from lib_layered_config.adapters.file_loaders.structured import TOMLFileLoader
from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.errors import InvalidFormatError
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

_RTOML_INSTALLED = importlib.util.find_spec("rtoml") is not None
_TOMLI_INSTALLED = importlib.util.find_spec("tomli") is not None
_TOMLLIB_PRESENT = importlib.util.find_spec("tomllib") is not None
_needs_rtoml = pytest.mark.skipif(not _RTOML_INSTALLED, reason="rtoml is not installed on this interpreter")
_needs_tomli = pytest.mark.skipif(not _TOMLI_INSTALLED, reason="tomli is not installed on this interpreter")
_needs_tomllib = pytest.mark.skipif(not _TOMLLIB_PRESENT, reason="tomllib needs Python 3.11")


def _stdlib_style_parsers() -> list[object]:
    params: list[object] = []
    if _TOMLLIB_PRESENT:
        params.append(pytest.param(TomliParser(importlib.import_module("tomllib")), id="tomllib"))
    if _TOMLI_INSTALLED:
        params.append(pytest.param(TomliParser(importlib.import_module("tomli")), id="tomli"))
    return params


def _parsers() -> list[object]:
    params = _stdlib_style_parsers()
    if _RTOML_INSTALLED:
        params.append(pytest.param(RtomlParser(importlib.import_module("rtoml")), id="rtoml"))
    return params


PARSERS = _parsers()
STDLIB_STYLE_PARSERS = _stdlib_style_parsers()


def _header_then_dotted(header: int, dotted: int) -> str:
    """A table header ``header`` keys deep holding a dotted key ``dotted`` keys deep: each within rtoml's 80.

    The document is ``1 + header + dotted - 1`` tables deep: the dotted key's last part names the value.
    """
    return "[" + ".".join(["a"] * header) + "]\n" + ".".join(["b"] * dotted) + " = 1\n"


def _array(depth: int) -> str:
    return "x = " + "[" * depth + "1" + "]" * depth + "\n"


#: The nesting forms rtoml counts, each building a document ``n`` levels deep.
_FORMS: dict[str, Callable[[int], str]] = {
    "array": _array,
    "inline-table": lambda n: "x = " + "{a = " * n + "1" + "}" * n + "\n",
    "table-header": lambda n: "[" + ".".join(["a"] * n) + "]\nk = 1\n",
    "dotted-key": lambda n: ".".join(["a"] * n) + " = 1\n",
    "array-of-tables": lambda n: "[[" + ".".join(["a"] * n) + "]]\nk = 1\n",
}


def _load_and_merge(parser: TomlParser, path: Path) -> dict[str, object]:
    """Read *path* the way ``read_config`` does: load it, then merge it as a layer."""
    data = TOMLFileLoader(parser).load(str(path))
    return merge_layers([LayerSnapshot(Layer.APP, data, str(path))]).data


def _nested_tables(levels: int) -> dict[str, object]:
    """A table ``levels`` deep, counting itself as level 1."""
    table: dict[str, object] = {"k": 1}
    for _ in range(levels - 1):
        table = {"a": table}
    return table


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize("form", list(_FORMS))
def test_nesting_rtoml_accepts_is_accepted(parser: TomlParser, form: str) -> None:
    assert isinstance(parser.loads(_FORMS[form](80)), dict)


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize("form", list(_FORMS))
def test_nesting_far_past_the_limit_is_too_deep(parser: TomlParser, form: str) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads(_FORMS[form](120))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
def test_an_array_nests_exactly_as_deep_as_rtoml_allows(parser: TomlParser) -> None:
    assert isinstance(parser.loads(_array(TOML_MAX_ARRAY_DEPTH)), dict)

    with pytest.raises(TomlLoadError) as caught:
        parser.loads(_array(TOML_MAX_ARRAY_DEPTH + 1))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.parametrize("parser", STDLIB_STYLE_PARSERS)
def test_tables_nest_exactly_as_deep_as_the_merge_allows(parser: TomlParser) -> None:
    assert TOML_MAX_TABLE_DEPTH == 101
    deepest = parser.loads(_header_then_dotted(51, 50))
    merge_layers([LayerSnapshot(Layer.APP, deepest, None)])

    with pytest.raises(TomlLoadError) as caught:
        parser.loads(_header_then_dotted(52, 50))
    with pytest.raises(InvalidFormatError):
        merge_layers([LayerSnapshot(Layer.APP, _nested_tables(TOML_MAX_TABLE_DEPTH + 1), None)])

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
def test_tables_deeper_than_the_merge_allows_are_refused_on_every_path(parser: TomlParser, tmp_path: Path) -> None:
    within = tmp_path / "within.toml"
    within.write_text(_header_then_dotted(50, 50), encoding="utf-8")
    beyond = tmp_path / "beyond.toml"
    beyond.write_text(_header_then_dotted(60, 60), encoding="utf-8")

    assert "a" in _load_and_merge(parser, within)
    with pytest.raises(InvalidFormatError):
        _load_and_merge(parser, beyond)


@os_agnostic
@pytest.mark.parametrize("parser", STDLIB_STYLE_PARSERS)
def test_the_stdlib_style_parsers_refuse_nesting_past_python_s_recursion_limit(parser: TomlParser) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads(_array(5000))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize(
    "text",
    ["x = = 1\n", "a = 1\na = 2\n", "a = " + "1" * 5000 + "\n", "a = 'unterminated\n", "a = 1e400\n", "a = -1e400\n"],
    ids=["eq", "duplicate", "5000-digits", "unterminated", "float-overflow", "negative-float-overflow"],
)
def test_a_malformed_document_is_refused_and_not_called_too_deep(parser: TomlParser, text: str) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads(text)

    assert caught.value.too_deep is False


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize(("literal", "sign"), [("inf", 1.0), ("+inf", 1.0), ("-inf", -1.0), ("1e-400", 0.0)])
def test_infinity_literals_and_an_underflow_still_load(parser: TomlParser, literal: str, sign: float) -> None:
    expected = sign * math.inf if sign else 0.0

    assert parser.loads(f"a = {literal}\n")["a"] == expected


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
def test_a_leading_byte_order_mark_is_skipped(parser: TomlParser, tmp_path: Path) -> None:
    path = tmp_path / "bom.toml"
    path.write_bytes(b"\xef\xbb\xbfa = 1\n")

    assert parser.loads(chr(0xFEFF) + "a = 1\n") == {"a": 1}
    assert TOMLFileLoader(parser).load(str(path)) == {"a": 1}


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
def test_a_syntax_error_names_its_line_and_column(parser: TomlParser) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads("a = 1\nb = 2\nc = = 3\n")

    assert caught.value.position is not None
    assert caught.value.position[0] == 3


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
def test_values_load_the_same(parser: TomlParser) -> None:
    loaded = parser.loads('a = 1\nb = "x"\nc = [1.5, true]\nd = nan\n[t]\ne = 2\n')

    assert {k: v for k, v in loaded.items() if k != "d"} == {"a": 1, "b": "x", "c": [1.5, True], "t": {"e": 2}}
    not_a_number = loaded["d"]
    assert isinstance(not_a_number, float)
    assert math.isnan(not_a_number)


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("a = 1979-05-27T07:32:00Z", "1979-05-27T07:32:00Z"),
        ("a = 1979-05-27T00:32:00.999999-07:00", "1979-05-27T00:32:00.999999-07:00"),
        ("a = 1979-05-27T07:32:00", "1979-05-27T07:32:00"),
        ("a = 1979-05-27", "1979-05-27"),
        ("a = 07:32:00", "07:32:00"),
    ],
    ids=["utc", "offset", "local-datetime", "date", "time"],
)
def test_dates_and_times_display_the_same(parser: TomlParser, text: str, shown: str) -> None:
    assert toml_value(parser.loads(text)["a"]) == shown


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS)
def test_an_integer_past_the_json_range_is_refused_by_the_loader(parser: TomlParser, tmp_path: Path) -> None:
    path = tmp_path / "wide.toml"
    path.write_text(f"n = {2**127}\n", encoding="utf-8")

    with pytest.raises(InvalidFormatError, match="holds an integer JSON cannot write"):
        TOMLFileLoader(parser).load(str(path))


#: TOML 1.1 additions rtoml reads: the ``\e`` escape, a newline inside an inline table, and a time
#: without seconds.
_TOML_1_1: dict[str, str] = {
    "escape-e": 'a = "x' + chr(92) + 'e"\n',
    "inline-table-newline": "a = {\n  b = 1,\n}\n",
    "time-without-seconds": "a = 07:32\n",
}


@os_agnostic
@pytest.mark.parametrize("text", list(_TOML_1_1.values()), ids=list(_TOML_1_1))
def test_the_parser_this_interpreter_uses_reads_toml_1_1(text: str) -> None:
    assert "a" in PARSER.loads(text)


def _reads_toml_1_1(parser: TomlParser) -> bool:
    try:
        parser.loads(_TOML_1_1["time-without-seconds"])
    except TomlLoadError:
        return False
    return True


#: Documents whose outcome through load-then-merge must not depend on the parser.
_CORPUS: dict[str, str] = {
    "plain": 'a = 1\nb = "x"\n[t]\nc = [1, 2.5, true]\n',
    "byte-order-mark": chr(0xFEFF) + "a = 1\n",
    "float-overflow": "a = 1e400\n",
    "infinity": "a = -inf\n",
    "integer-past-128-bits": f"a = {2**130}\n",
    "tables-at-the-merge-bound": _header_then_dotted(51, 50),
    "tables-one-past-the-merge-bound": _header_then_dotted(52, 50),
    "tables-past-the-merge-bound": _header_then_dotted(60, 60),
    "array-at-rtoml-s-limit": _array(80),
    "array-past-rtoml-s-limit": _array(81),
    "array-under-deep-tables": "[" + ".".join(["a"] * 80) + "]\n" + _array(80),
    **_TOML_1_1,
}


def _outcome(parser: TomlParser, path: Path) -> object:
    try:
        return _load_and_merge(parser, path)
    except InvalidFormatError:
        return "refused"


@os_agnostic
@_needs_rtoml
@pytest.mark.parametrize("parser", STDLIB_STYLE_PARSERS)
@pytest.mark.parametrize("name", list(_CORPUS))
def test_every_parser_reads_the_corpus_as_rtoml_does(parser: TomlParser, name: str, tmp_path: Path) -> None:
    if name in _TOML_1_1 and not _reads_toml_1_1(parser):
        pytest.skip("this tomllib reads TOML 1.0; it parses only where rtoml or tomli is absent")
    rtoml = RtomlParser(importlib.import_module("rtoml"))
    path = tmp_path / f"{name}.toml"
    path.write_text(_CORPUS[name], encoding="utf-8")

    assert _outcome(parser, path) == _outcome(rtoml, path)


def _never(name: str) -> Callable[[], ModuleType | None]:
    def _importer() -> ModuleType | None:
        raise AssertionError(f"{name} must not be imported here")

    return _importer


def _absent() -> ModuleType | None:
    return None


def _real(name: str) -> Callable[[], ModuleType | None]:
    module = importlib.import_module(name)

    def _importer() -> ModuleType | None:
        return module

    return _importer


@os_agnostic
@_needs_tomli
def test_a_free_threaded_interpreter_never_imports_rtoml() -> None:
    parser = select_parser(
        free_threaded=True, import_rtoml=_never("rtoml"), import_tomli=_real("tomli"), import_tomllib=_never("tomllib")
    )

    assert isinstance(parser, TomliParser)


@os_agnostic
@_needs_tomli
def test_without_rtoml_tomli_is_chosen_over_tomllib() -> None:
    parser = select_parser(
        free_threaded=False, import_rtoml=_absent, import_tomli=_real("tomli"), import_tomllib=_never("tomllib")
    )

    assert isinstance(parser, TomliParser)


@os_agnostic
@_needs_tomllib
def test_without_rtoml_and_tomli_tomllib_is_chosen() -> None:
    parser = select_parser(
        free_threaded=False, import_rtoml=_absent, import_tomli=_absent, import_tomllib=_real("tomllib")
    )

    assert isinstance(parser, TomliParser)


@os_agnostic
@_needs_rtoml
def test_with_rtoml_and_the_gil_rtoml_is_chosen() -> None:
    parser = select_parser(
        free_threaded=False, import_rtoml=_real("rtoml"), import_tomli=_never("tomli"), import_tomllib=_never("tomllib")
    )

    assert isinstance(parser, RtomlParser)


@os_agnostic
def test_with_no_parser_the_import_says_what_to_install() -> None:
    with pytest.raises(ImportError, match="pip install rtoml"):
        select_parser(free_threaded=False, import_rtoml=_absent, import_tomli=_absent, import_tomllib=_absent)
