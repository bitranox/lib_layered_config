"""A TOML or YAML integer outside JSON's range refuses the file.

orjson writes an integer only from -2**63 to 2**64-1. rtoml reads up to 128 bits and PyYAML reads a
hex literal of any width, so a config holding a wider integer loaded and then crashed every JSON
view (``Config.to_json``, ``read_config_json``, ``display_config`` in JSON) with an uncaught
``TypeError: Integer exceeds 64-bit range``. The loader refuses the file instead, naming the file,
where each such integer sits and its width, never its digits - the rule ``!!set`` and ``!!binary``
already follow. JSON itself never reaches it: orjson reads a wide integer as a float.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.file_loaders.structured import TOMLFileLoader, YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None
_needs_yaml = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")

_SMALLEST = -(2**63)
_LARGEST = 2**64 - 1


def _toml_refusal(tmp_path: Path, text: str) -> tuple[str, str]:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidFormatError) as caught:
        TOMLFileLoader().load(str(path))
    return str(path), str(caught.value)


@os_agnostic
@pytest.mark.parametrize("value", [_SMALLEST, -1, 0, _LARGEST])
def test_a_toml_integer_json_can_write_still_loads(tmp_path: Path, value: int) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"[db]\nport = {value}\n", encoding="utf-8")

    assert TOMLFileLoader().load(str(path)) == {"db": {"port": value}}


@os_agnostic
@pytest.mark.parametrize(("value", "bits"), [(_LARGEST + 1, 65), (_SMALLEST - 1, 64), (2**127, 128)])
def test_a_toml_integer_outside_json_range_refuses_the_file(tmp_path: Path, value: int, bits: int) -> None:
    path, message = _toml_refusal(tmp_path, f"[db]\nport = {value}\n")

    assert path in message
    assert message.endswith(f": db.port (int, {bits} bits)")
    assert str(abs(value)) not in message


@os_agnostic
def test_every_wide_toml_integer_is_named_including_inside_arrays(tmp_path: Path) -> None:
    _, message = _toml_refusal(tmp_path, f"a = {2**70}\n[b]\nsizes = [1, {2**80}]\n")

    assert message.endswith(": a (int, 71 bits); b.sizes.1 (int, 81 bits)")


@os_agnostic
@_needs_yaml
def test_a_wide_yaml_hex_literal_refuses_the_file_without_its_digits(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("history:\n  path: 0x" + "F" * 4000 + "\n  small: 42\n", encoding="utf-8")

    with pytest.raises(InvalidFormatError) as caught:
        YAMLFileLoader().load(str(path))
    message = str(caught.value)

    assert str(path) in message
    assert message.endswith(": history.path (int, 16000 bits)")
    assert "FFFF" not in message


@os_agnostic
@_needs_yaml
def test_a_yaml_integer_json_can_write_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(f"db:\n  port: {_LARGEST}\n  low: {_SMALLEST}\n  flag: true\n", encoding="utf-8")

    assert YAMLFileLoader().load(str(path)) == {"db": {"port": _LARGEST, "low": _SMALLEST, "flag": True}}


@os_agnostic
def test_read_config_refuses_a_layer_holding_a_wide_integer(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(f"[h]\np = {2**70}\n", encoding="utf-8")

    # start_dir keeps the .env search inside tmp_path, away from the repository's own .env.
    with pytest.raises((InvalidFormatError, LayerLoadError)) as caught:
        read_config(vendor="Acme", app="Demo", slug="demo", default_file=defaults, start_dir=str(tmp_path))

    assert "h.p (int, 71 bits)" in str(caught.value)
