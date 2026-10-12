"""A file nested deeper than its parser allows says so, rather than calling the file invalid.

Every parser stops at some nesting depth: rtoml at 80 levels, orjson at 1024, PyYAML at Python's
recursion limit. Reported as "<path> is not valid TOML", a well-formed file reads as broken and the
user goes looking for a typo. The refusal names the depth instead, with the position when the
parser gives one; a genuinely malformed file keeps the "is not valid" message.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config.application.ports import FileLoader

_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None
_needs_yaml = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")


def _refusal(tmp_path: Path, name: str, text: str, loader: FileLoader) -> tuple[str, str]:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidFormatError) as caught:
        loader.load(str(path))
    return str(path), str(caught.value)


@os_agnostic
@pytest.mark.parametrize(
    ("text", "where"),
    [
        ("x = " + "[" * 120 + "1" + "]" * 120 + "\n", " (line 1, column 85)"),
        ("x = " + "{a = " * 120 + "1" + "}" * 120 + "\n", " (line 1, column 405)"),
        ("[" + ".".join(["a"] * 120) + "]\nk = 1\n", ""),
        (".".join(["a"] * 120) + " = 1\n", ""),
    ],
    ids=["array", "inline-table", "table-header", "dotted-key"],
)
def test_a_toml_file_nested_too_deep_says_so(tmp_path: Path, text: str, where: str) -> None:
    path, message = _refusal(tmp_path, "deep.toml", text, TOMLFileLoader())

    assert message == f"{path} nests deeper than the TOML parser allows{where}"


@os_agnostic
def test_a_json_file_nested_too_deep_says_so(tmp_path: Path) -> None:
    path, message = _refusal(tmp_path, "deep.json", '{"x": ' + "[" * 1100 + "]" * 1100 + "}", JSONFileLoader())

    assert message.startswith(f"{path} nests deeper than the JSON parser allows (line 1, column ")


@_needs_yaml
@os_agnostic
def test_a_yaml_file_nested_too_deep_says_so(tmp_path: Path) -> None:
    path, message = _refusal(tmp_path, "deep.yaml", "x: " + "[" * 3000 + "]" * 3000 + "\n", YAMLFileLoader())

    assert message == f"{path} nests deeper than the YAML parser allows"


@os_agnostic
@pytest.mark.parametrize(
    ("name", "text", "loader"),
    [
        ("bad.toml", "x = = 1\n", TOMLFileLoader()),
        ("bad.json", '{"x": }', JSONFileLoader()),
        pytest.param("bad.yaml", "x: [1, 2\n", YAMLFileLoader(), marks=_needs_yaml),
    ],
    ids=["toml", "json", "yaml"],
)
def test_a_malformed_file_is_still_called_invalid(tmp_path: Path, name: str, text: str, loader: FileLoader) -> None:
    path, message = _refusal(tmp_path, name, text, loader)

    assert message.startswith(f"{path} is not valid ")
