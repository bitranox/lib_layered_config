"""A key repeated in one table of a JSON or YAML file is refused, as TOML already refuses it.

Both parsers keep the last value without a word, so a copy-pasted block silently replaced the
setting above it. The refusal names the file and the dotted position of every repeated key (YAML
adds its line and column), never a value, which may be a secret.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, YAMLFileLoader
from lib_layered_config.core import LayerLoadError
from lib_layered_config.domain.errors import InvalidFormatError
from lib_layered_config.domain.json_codec import JsonCodec, OrjsonCodec, StdlibCodec
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Probe"
SLUG = "dup-probe"
REPEATS = "repeats a key, and only its last value would load"

_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None
_needs_yaml = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is not installed on this interpreter")


def _codecs() -> list[JsonCodec]:
    codecs: list[JsonCodec] = [StdlibCodec()]
    if importlib.util.find_spec("orjson") is not None:
        codecs.append(OrjsonCodec(importlib.import_module("orjson")))
    return codecs


def _codec_id(codec: JsonCodec) -> str:
    return type(codec).__name__


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@os_agnostic
@pytest.mark.parametrize("codec", _codecs(), ids=_codec_id)
@pytest.mark.parametrize(
    ("text", "positions"),
    [
        ('{"a": 1, "a": 2}', "a"),
        ('{"service": {"port": 1, "host": "h", "port": 2}}', "service.port"),
        ('{"items": [{"name": "x", "name": "y"}]}', "items.0.name"),
        ('{"b": 1, "b": 2, "c": {"d": 1, "d": 2}}', "b; c.d"),
    ],
)
def test_a_json_file_repeating_a_key_is_refused_naming_each_position(
    tmp_path: Path, codec: JsonCodec, text: str, positions: str
) -> None:
    path = _write(tmp_path, "config.json", text)

    with pytest.raises(InvalidFormatError) as caught:
        JSONFileLoader(codec).load(str(path))

    assert str(caught.value) == f"{path} {REPEATS}: {positions}"


@os_agnostic
@pytest.mark.parametrize("codec", _codecs(), ids=_codec_id)
def test_a_json_refusal_never_carries_a_value(tmp_path: Path, codec: JsonCodec) -> None:
    path = _write(tmp_path, "config.json", '{"password": "hunter2", "password": "s3cret"}')

    with pytest.raises(InvalidFormatError) as caught:
        JSONFileLoader(codec).load(str(path))

    assert "hunter2" not in str(caught.value)
    assert "s3cret" not in str(caught.value)


@os_agnostic
@pytest.mark.parametrize("codec", _codecs(), ids=_codec_id)
def test_the_same_name_in_different_tables_or_case_still_loads(tmp_path: Path, codec: JsonCodec) -> None:
    path = _write(tmp_path, "config.json", '{"a": {"x": 1}, "b": {"x": 2}, "Key": 1, "key": 2}')

    assert JSONFileLoader(codec).load(str(path)) == {"a": {"x": 1}, "b": {"x": 2}, "Key": 1, "key": 2}


@os_agnostic
@_needs_yaml
@pytest.mark.parametrize(
    ("text", "positions"),
    [
        ("a: 1\na: 2\n", "a (line 2, column 1)"),
        ("service:\n  port: 1\n  host: h\n  port: 2\n", "service.port (line 4, column 3)"),
        ('a: 1\n"a": 2\n', "a (line 2, column 1)"),
        ("items:\n  - name: x\n    name: y\n", "items.0.name (line 3, column 5)"),
    ],
)
def test_a_yaml_file_repeating_a_key_is_refused_naming_each_position(tmp_path: Path, text: str, positions: str) -> None:
    path = _write(tmp_path, "config.yaml", text)

    with pytest.raises(InvalidFormatError) as caught:
        YAMLFileLoader().load(str(path))

    assert str(caught.value) == f"{path} {REPEATS}: {positions}"


@os_agnostic
@_needs_yaml
def test_a_yaml_refusal_never_carries_a_value(tmp_path: Path) -> None:
    path = _write(tmp_path, "config.yaml", "password: hunter2\npassword: s3cret\n")

    with pytest.raises(InvalidFormatError) as caught:
        YAMLFileLoader().load(str(path))

    assert "hunter2" not in str(caught.value)
    assert "s3cret" not in str(caught.value)


@os_agnostic
@_needs_yaml
def test_yaml_merge_keys_are_not_repeated_keys(tmp_path: Path) -> None:
    """``<<`` may appear twice in one mapping, and overriding what it merges in is its purpose."""
    text = "base: &base\n  x: 1\n  y: 1\nextra: &extra\n  z: 1\nderived:\n  <<: *base\n  <<: *extra\n  x: 2\n"
    path = _write(tmp_path, "config.yaml", text)

    loaded = YAMLFileLoader().load(str(path))

    assert loaded["derived"]["x"] == 2
    assert loaded["derived"]["y"] == 1


@os_agnostic
def test_read_config_refuses_a_default_file_repeating_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_file = _write(tmp_path, "defaults.json", '{"db": {"host": "a", "host": "b"}}')
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    with pytest.raises(LayerLoadError) as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)

    assert f"{default_file} {REPEATS}: db.host" in str(caught.value)
