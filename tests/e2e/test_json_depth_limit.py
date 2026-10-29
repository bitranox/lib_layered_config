"""A value nested deeper than JSON output can write.

orjson, and the stdlib codec matching it, write at most 254 levels, and ``read_config_json`` wraps
the config in one more, so a config may nest 253 levels counted from its top-level table. Deeper
values used to load and then crash every JSON view with ``TypeError: Recursion limit reached``.
An environment or ``.env`` value that deep now stays the text it was written as, and a file that
deep is refused, the rule an integer outside JSON's range already follows.
"""

from __future__ import annotations

import importlib.util
import json
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config, read_config_json
from lib_layered_config.core import LayerLoadError
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Probe"
SLUG = "depth-probe"
PREFIX = "DEPTH_PROBE___"

_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None


def _nested(depth: int) -> str:
    return "[" * depth + "1" + "]" * depth


def _read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> object:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)
    return read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), **kwargs)  # type: ignore[arg-type]


@os_agnostic
def test_an_env_value_at_the_limit_loads_as_a_list_and_every_json_view_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{PREFIX}DEEP", _nested(252))
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path))

    assert isinstance(config.get("deep"), list)
    assert json.loads(config.to_json())["deep"] == json.loads(_nested(252))
    assert "deep" in json.loads(read_config_json(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path)))["config"]


@os_agnostic
def test_an_env_value_past_the_limit_stays_the_text_it_was_written_as(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{PREFIX}DEEP", _nested(253))
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path))

    assert config.get("deep") == _nested(253)
    assert json.loads(read_config_json(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path)))["config"][
        "deep"
    ] == _nested(253)


@os_agnostic
@pytest.mark.parametrize(("depth", "expected_type"), [(250, list), (251, str)])
def test_the_limit_counts_the_levels_the_key_itself_adds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, depth: int, expected_type: type
) -> None:
    """``A__B__DEEP`` puts the value three tables down, so it may nest two levels less."""
    monkeypatch.setenv(f"{PREFIX}A__B__DEEP", _nested(depth))
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path))

    assert type(config.get("a.b.deep")) is expected_type
    json.loads(read_config_json(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path)))


@os_agnostic
def test_a_dotenv_value_past_the_limit_stays_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"DEEP={_nested(253)}\n", encoding="utf-8")
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path=str(dotenv))

    assert config.get("deep") == _nested(253)


@os_agnostic
def test_a_json_file_past_the_limit_is_refused_naming_file_position_and_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default_file = tmp_path / "defaults.json"
    default_file.write_text('{"service": {"deep": ' + _nested(252) + "}}", encoding="utf-8")
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    with pytest.raises(LayerLoadError, match=r"nests service\.deep 254 levels deep; JSON output takes 253") as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)

    assert str(default_file) in str(caught.value)


@os_agnostic
def test_a_json_file_at_the_limit_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_file = tmp_path / "defaults.json"
    default_file.write_text('{"service": {"deep": ' + _nested(251) + "}}", encoding="utf-8")
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)

    json.loads(read_config_json(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file))
    assert isinstance(config.get("service.deep"), list)


@os_agnostic
@pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional dependency")
def test_a_yaml_file_past_the_limit_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_file = tmp_path / "defaults.yaml"
    default_file.write_text("deep: " + _nested(253) + "\n", encoding="utf-8")
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    with pytest.raises(LayerLoadError, match=r"nests deep 254 levels deep; JSON output takes 253"):
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)
