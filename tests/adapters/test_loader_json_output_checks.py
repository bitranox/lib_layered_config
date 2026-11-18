"""Every refusal the TOML and JSON loaders make after parsing still fires, with its exact message.

After a parse the TOML loader refuses an integer JSON cannot write and a nesting JSON output cannot
write; the JSON loader refuses that nesting and a key repeated in one object. Each check names
positions, and building a position string for every node of every file cost more than the parse
itself, so a cheap walk without positions runs first and the positioned check runs only when that
walk finds something. A walk that missed a case would let a bad file through, so each case here
sits at or next to its boundary and its message is compared whole.

The TOML cases hand the loader an already-parsed document through its parser seam: no TOML backend
nests 254 levels, and the check must still hold for whatever a parser returns.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from lib_layered_config.domain.json_codec import JsonCodec, OrjsonCodec, StdlibCodec
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_DEPTH = 253
_WIDE = "holds an integer JSON cannot write (it takes -2**63 to 2**64-1); write it as a string instead"


class _Parsed:
    """A TOML parser double returning one prepared document, whatever the text."""

    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def loads(self, text: str) -> dict[str, object]:
        del text
        return self._document


def _lists(depth: int) -> object:
    """*depth* lists nested around ``1``."""
    value: object = 1
    for _ in range(depth):
        value = [value]
    return value


def _tables(depth: int) -> dict[str, object]:
    """*depth* tables nested under the key ``k``, the innermost empty."""
    value: dict[str, object] = {}
    for _ in range(depth - 1):
        value = {"k": value}
    return value


def _toml(tmp_path: Path, document: dict[str, object]) -> tuple[Path, TOMLFileLoader]:
    path = tmp_path / "config.toml"
    path.write_text("# parsed by the double\n", encoding="utf-8")
    return path, TOMLFileLoader(_Parsed(document))


def _toml_refusal(tmp_path: Path, document: dict[str, object]) -> str:
    path, loader = _toml(tmp_path, document)
    with pytest.raises(InvalidFormatError) as caught:
        loader.load(path)
    return str(caught.value).replace(str(path), "<path>")


def _nesting(where: str, depth: int) -> str:
    return (
        f"<path> nests {where} {depth} levels deep; JSON output takes {_DEPTH}, counted from the top-level "
        "table: flatten it, or write it as a string"
    )


@os_agnostic
@pytest.mark.parametrize(
    "document",
    [
        {"ok": [True, False, 2**64 - 1, -(2**63)], "n": 0},
        {"deep": _lists(_DEPTH - 1)},
        _tables(_DEPTH),
        {"a": [{"b": _lists(_DEPTH - 3)}]},
    ],
    ids=["integers at the bounds", "lists at the depth", "tables at the depth", "list of tables at the depth"],
)
def test_a_toml_document_at_the_bounds_loads(tmp_path: Path, document: dict[str, object]) -> None:
    path, loader = _toml(tmp_path, document)

    assert loader.load(path) == document


@os_agnostic
@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"a": 2**64}, f"<path> {_WIDE}: a (int, 65 bits)"),
        ({"t": {"list": [1, [2, -(2**63) - 1]]}}, f"<path> {_WIDE}: t.list.1.1 (int, 64 bits)"),
        ({"x": [2**200], "a": {"b": -(2**64)}}, f"<path> {_WIDE}: a.b (int, 65 bits); x.0 (int, 201 bits)"),
        ({"deep": _lists(_DEPTH)}, _nesting("deep", _DEPTH + 1)),
        (_tables(_DEPTH + 1), _nesting(".".join(["k"] * _DEPTH), _DEPTH + 1)),
        ({"a": [{"b": _lists(_DEPTH - 2)}]}, _nesting("a", _DEPTH + 1)),
        ({"deep": _lists(_DEPTH), "wide": 2**64}, f"<path> {_WIDE}: wide (int, 65 bits)"),
    ],
    ids=[
        "wide at the top",
        "narrow negative in a nested list",
        "several, sorted",
        "lists one past the depth",
        "tables one past the depth",
        "list of tables one past the depth",
        "a wide integer is refused before the depth",
    ],
)
def test_a_toml_document_past_a_bound_is_refused_with_its_message(
    tmp_path: Path, document: dict[str, object], message: str
) -> None:
    assert _toml_refusal(tmp_path, document) == message


def _json_codecs() -> list[JsonCodec]:
    codecs: list[JsonCodec] = [StdlibCodec()]
    if importlib.util.find_spec("orjson") is not None:
        codecs.append(OrjsonCodec(importlib.import_module("orjson")))
    return codecs


def _arrays(depth: int) -> str:
    return "[" * depth + "1" + "]" * depth


@os_agnostic
@pytest.mark.parametrize("codec", _json_codecs(), ids=lambda codec: type(codec).__name__)
@pytest.mark.parametrize(
    "text",
    ['{"deep": ' + _arrays(_DEPTH - 1) + "}", '{"a": {"x": 1}, "b": {"x": 2}, "c": [{"x": 1}, {"x": 2}]}'],
    ids=["arrays at the depth", "the same key in different objects"],
)
def test_a_json_document_at_the_bounds_loads(tmp_path: Path, codec: JsonCodec, text: str) -> None:
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")

    assert JSONFileLoader(codec).load(path) == codec.loads(text)


@os_agnostic
@pytest.mark.parametrize("codec", _json_codecs(), ids=lambda codec: type(codec).__name__)
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"deep": ' + _arrays(_DEPTH) + "}", _nesting("deep", _DEPTH + 1)),
        (
            '{"a": 1, "b": {"c": 1, "c": 2}, "a": 3, "d": [{"e": 1, "e": 2}]}',
            "<path> repeats a key, and only its last value would load: a; b.c; d.0.e",
        ),
        ('{"x": [[{"k": 1, "k": 1}]]}', "<path> repeats a key, and only its last value would load: x.0.0.k"),
        ('{"deep": ' + _arrays(_DEPTH) + ', "a": 1, "a": 2}', _nesting("deep", _DEPTH + 1)),
    ],
    ids=["arrays one past the depth", "repeats at three places", "a repeat deep in lists", "depth before repeats"],
)
def test_a_json_document_past_a_bound_is_refused_with_its_message(
    tmp_path: Path, codec: JsonCodec, text: str, message: str
) -> None:
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(InvalidFormatError) as caught:
        JSONFileLoader(codec).load(path)

    assert str(caught.value).replace(str(path), "<path>") == message
