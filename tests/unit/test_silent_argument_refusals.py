"""Arguments that used to give a silently wrong answer, or broke a documented contract, are refused.

Each case below once returned a plausible result rather than failing: an unknown display format
rendered the human view, a ``prefer`` given as one string was read letter by letter (so it
preferred nothing), ``is_valid_profile_name`` raised on a non-string although it promises not to,
and an empty slug produced the prefix ``___``. A wrongly typed identifier elsewhere still raises
the interpreter's own error; a type checker already flags those calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from lib_layered_config import (
    Config,
    OutputFormat,
    ValidationError,
    display_config,
    is_valid_profile_name,
    read_config,
    read_config_json,
    read_config_raw,
)
from lib_layered_config.adapters.env.default import default_env_prefix
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _untyped(value: object) -> Any:
    """Hand *value* past the type checker, as an untyped caller would."""
    return cast("Any", value)


@os_agnostic
@pytest.mark.parametrize("output_format", ["xml", "JSON", ""])
def test_display_config_refuses_an_unknown_output_format(output_format: str) -> None:
    with pytest.raises(ValueError, match=r"output_format must be one of 'human', 'json'"):
        display_config(Config({}, {}), output_format=_untyped(output_format))


@os_agnostic
def test_display_config_still_takes_the_format_as_its_text(capsys: pytest.CaptureFixture[str]) -> None:
    display_config(Config({"a": 1}, {}), output_format=_untyped("json"))
    assert capsys.readouterr().out.strip().startswith("{")


@os_agnostic
@pytest.mark.parametrize("output_format", [OutputFormat.HUMAN, OutputFormat.JSON])
def test_display_config_renders_each_known_format(
    output_format: OutputFormat, capsys: pytest.CaptureFixture[str]
) -> None:
    display_config(Config({"a": 1}, {}), output_format=output_format)
    output = capsys.readouterr().out
    assert output.strip().startswith("{") is (output_format is OutputFormat.JSON)


_READERS: list[Callable[..., object]] = [read_config, read_config_json, read_config_raw]


@os_agnostic
@pytest.mark.parametrize("reader", _READERS, ids=lambda reader: reader.__name__)
def test_every_read_refuses_prefer_given_as_one_string(reader: Callable[..., object], tmp_path: Path) -> None:
    with pytest.raises(TypeError, match=r"prefer takes a sequence of suffixes, not a single str: write \['toml'\]"):
        reader(vendor="Acme", app="Demo", slug="silent-args", prefer=_untyped("toml"), start_dir=str(tmp_path))


@os_agnostic
@pytest.mark.parametrize("value", [5, 1.5, b"prod", ["prod"]], ids=["int", "float", "bytes", "list"])
def test_is_valid_profile_name_answers_false_for_a_non_string(value: object) -> None:
    assert is_valid_profile_name(_untyped(value)) is False


@os_agnostic
def test_default_env_prefix_refuses_an_empty_slug() -> None:
    with pytest.raises(ValidationError, match=r"^slug cannot be empty$"):
        default_env_prefix("")


@os_agnostic
def test_default_env_prefix_still_builds_the_prefix_for_a_slug() -> None:
    assert default_env_prefix("config-kit") == "CONFIG_KIT___"
