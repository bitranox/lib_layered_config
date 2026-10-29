"""The stdlib TOML parser answers like rtoml, so a TOML file loads or is refused the same everywhere.

rtoml has no free-threaded build, and from Python 3.14 it is an optional extra, so many interpreters
parse TOML with the standard library's ``tomllib`` (Python 3.11+). Each test runs against every
parser this interpreter has. rtoml stops at 80 levels of nesting; tomllib only at Python's recursion
limit, so the stdlib parser refuses a document deeper than :data:`TOML_MAX_DEPTH` levels, the
smallest bound that never refuses a document rtoml accepts.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.display.toml_text import toml_value
from lib_layered_config.adapters.file_loaders._toml_backend import (
    TOML_MAX_DEPTH,
    RtomlParser,
    StdlibTomlParser,
    TomlLoadError,
    TomlParser,
    select_parser,
)
from lib_layered_config.adapters.file_loaders.structured import TOMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

_RTOML_INSTALLED = importlib.util.find_spec("rtoml") is not None
_TOMLLIB_PRESENT = importlib.util.find_spec("tomllib") is not None


def _parsers() -> list[TomlParser]:
    parsers: list[TomlParser] = []
    if _TOMLLIB_PRESENT:
        parsers.append(StdlibTomlParser(importlib.import_module("tomllib")))
    if _RTOML_INSTALLED:
        parsers.append(RtomlParser(importlib.import_module("rtoml")))
    return parsers


PARSERS = _parsers()


def _parser_id(parser: TomlParser) -> str:
    return type(parser).__name__


#: The nesting forms rtoml counts, each building a document ``n`` levels deep.
_FORMS: dict[str, Callable[[int], str]] = {
    "array": lambda n: "x = " + "[" * n + "1" + "]" * n + "\n",
    "inline-table": lambda n: "x = " + "{a = " * n + "1" + "}" * n + "\n",
    "table-header": lambda n: "[" + ".".join(["a"] * n) + "]\nk = 1\n",
    "dotted-key": lambda n: ".".join(["a"] * n) + " = 1\n",
    "array-of-tables": lambda n: "[[" + ".".join(["a"] * n) + "]]\nk = 1\n",
}


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
@pytest.mark.parametrize("form", list(_FORMS))
def test_nesting_rtoml_accepts_is_accepted(parser: TomlParser, form: str) -> None:
    assert isinstance(parser.loads(_FORMS[form](80)), dict)


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
@pytest.mark.parametrize("form", list(_FORMS))
def test_nesting_far_past_the_limit_is_too_deep(parser: TomlParser, form: str) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads(_FORMS[form](120))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.skipif(not _TOMLLIB_PRESENT, reason="tomllib needs Python 3.11")
def test_the_stdlib_parser_refuses_nesting_past_python_s_recursion_limit() -> None:
    parser = StdlibTomlParser(importlib.import_module("tomllib"))

    with pytest.raises(TomlLoadError) as caught:
        parser.loads(_FORMS["array"](5000))

    assert caught.value.too_deep is True


@os_agnostic
@pytest.mark.skipif(not _TOMLLIB_PRESENT, reason="tomllib needs Python 3.11")
def test_the_stdlib_bound_sits_on_the_deepest_document_rtoml_accepts() -> None:
    parser = StdlibTomlParser(importlib.import_module("tomllib"))

    assert isinstance(parser.loads(_FORMS["array-of-tables"](80)), dict)
    with pytest.raises(TomlLoadError):
        parser.loads(_FORMS["array-of-tables"](81))
    assert TOML_MAX_DEPTH == 82


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
@pytest.mark.parametrize(
    "text",
    ["x = = 1\n", "a = 1\na = 2\n", "a = " + "1" * 5000 + "\n", "a = 'unterminated\n"],
    ids=["eq", "duplicate", "5000-digits", "unterminated"],
)
def test_a_malformed_document_is_refused_and_not_called_too_deep(parser: TomlParser, text: str) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads(text)

    assert caught.value.too_deep is False


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
def test_a_syntax_error_names_its_line_and_column(parser: TomlParser) -> None:
    with pytest.raises(TomlLoadError) as caught:
        parser.loads("a = 1\nb = 2\nc = = 3\n")

    assert caught.value.position is not None
    assert caught.value.position[0] == 3


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
def test_values_load_the_same(parser: TomlParser) -> None:
    loaded = parser.loads('a = 1\nb = "x"\nc = [1.5, true]\nd = nan\n[t]\ne = 2\n')

    assert {k: v for k, v in loaded.items() if k != "d"} == {"a": 1, "b": "x", "c": [1.5, True], "t": {"e": 2}}
    not_a_number = loaded["d"]
    assert isinstance(not_a_number, float)
    assert math.isnan(not_a_number)


@os_agnostic
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
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
@pytest.mark.parametrize("parser", PARSERS, ids=_parser_id)
def test_an_integer_past_the_json_range_is_refused_by_the_loader(parser: TomlParser, tmp_path: Path) -> None:
    path = tmp_path / "wide.toml"
    path.write_text(f"n = {2**127}\n", encoding="utf-8")

    with pytest.raises(InvalidFormatError, match="holds an integer JSON cannot write"):
        TOMLFileLoader(parser).load(str(path))


def _never_import() -> ModuleType | None:
    raise AssertionError("rtoml must not be imported on a free-threaded interpreter")


def _absent() -> ModuleType | None:
    return None


@os_agnostic
@pytest.mark.skipif(not _TOMLLIB_PRESENT, reason="tomllib needs Python 3.11")
def test_a_free_threaded_interpreter_never_imports_rtoml() -> None:
    tomllib = importlib.import_module("tomllib")

    def _tomllib() -> ModuleType | None:
        return tomllib

    assert isinstance(
        select_parser(free_threaded=True, import_rtoml=_never_import, import_tomllib=_tomllib), StdlibTomlParser
    )


@os_agnostic
@pytest.mark.skipif(not _TOMLLIB_PRESENT, reason="tomllib needs Python 3.11")
def test_without_rtoml_tomllib_is_chosen() -> None:
    tomllib = importlib.import_module("tomllib")

    def _tomllib() -> ModuleType | None:
        return tomllib

    assert isinstance(
        select_parser(free_threaded=False, import_rtoml=_absent, import_tomllib=_tomllib), StdlibTomlParser
    )


@os_agnostic
@pytest.mark.skipif(not _RTOML_INSTALLED, reason="rtoml is not installed on this interpreter")
def test_with_rtoml_and_the_gil_rtoml_is_chosen() -> None:
    rtoml = importlib.import_module("rtoml")

    def _rtoml() -> ModuleType | None:
        return rtoml

    assert isinstance(select_parser(free_threaded=False, import_rtoml=_rtoml, import_tomllib=_absent), RtomlParser)


@os_agnostic
def test_with_neither_parser_the_import_says_what_to_install() -> None:
    with pytest.raises(ImportError, match="pip install rtoml"):
        select_parser(free_threaded=False, import_rtoml=_absent, import_tomllib=_absent)
