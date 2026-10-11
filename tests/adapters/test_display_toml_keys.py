"""The human display shows every key, whatever its name, with the provenance of its value.

The display used to serialise the configuration to TOML and re-parse that text line by line, so
every line its two patterns did not expect vanished: a key TOML must quote (a space, a dot, a
non-ASCII letter, the empty name), an array of tables, and the provenance of any key under a
quoted section name. Each case below is a shape a configuration file can legitimately hold.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from lib_layered_config import Config, OutputFormat, display_config
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from lib_layered_config.domain.config import SourceInfo

# Wide enough that no line is clipped, so an absent line is absent and not cut off.
_WIDTH = 500


def _source(key: str) -> SourceInfo:
    return {"layer": "app", "path": f"/etc/app/{key}.toml", "key": key}


def _config(data: dict[str, Any], *dotted_keys: str) -> Config:
    return Config(data, {key: _source(key) for key in dotted_keys})


def _render(config: Config, *, section: str | None = None) -> list[str]:
    buffer = io.StringIO()
    console = Console(file=buffer, width=_WIDTH, no_color=True, highlight=False)
    display_config(config, output_format=OutputFormat.HUMAN, section=section, console=console)
    return [line.strip() for line in buffer.getvalue().splitlines() if line.strip()]


def _source_line(key: str) -> str:
    return f"# layer:app profile:none (/etc/app/{key}.toml)"


def _assert_shown_with_source(lines: list[str], *, line: str, dotted_key: str) -> None:
    assert line in lines, f"{line!r} missing from {lines}"
    assert lines[lines.index(line) - 1] == _source_line(dotted_key)


@os_agnostic
@pytest.mark.parametrize(
    ("key", "shown"),
    [
        pytest.param("a b", '"a b"', id="space"),
        pytest.param("a.b", '"a.b"', id="dot"),
        pytest.param("ü", '"ü"', id="non-ascii"),
        pytest.param("", '""', id="empty"),
        pytest.param('say "hi"', '"say \\"hi\\""', id="quote"),
    ],
)
def test_a_key_toml_must_quote_is_shown_quoted_with_its_source(key: str, shown: str) -> None:
    lines = _render(_config({"probe": {key: 1, "ok": 2}}, f"probe.{key}", "probe.ok"))

    _assert_shown_with_source(lines, line=f"{shown} = 1", dotted_key=f"probe.{key}")
    _assert_shown_with_source(lines, line="ok = 2", dotted_key="probe.ok")


@os_agnostic
def test_a_root_key_toml_must_quote_is_shown() -> None:
    lines = _render(_config({"a b": 1}, "a b"))

    _assert_shown_with_source(lines, line='"a b" = 1', dotted_key="a b")


@os_agnostic
def test_a_key_under_a_quoted_section_name_shows_its_source() -> None:
    lines = _render(_config({"sec tion": {"k": 1}}, "sec tion.k"))

    assert '["sec tion"]' in lines
    _assert_shown_with_source(lines, line="k = 1", dotted_key="sec tion.k")


@os_agnostic
def test_a_key_under_a_nested_quoted_table_shows_its_source() -> None:
    lines = _render(_config({"deep": {"x": {"y z": {"w": 1}}}}, "deep.x.y z.w"))

    assert '[deep.x."y z"]' in lines
    _assert_shown_with_source(lines, line="w = 1", dotted_key="deep.x.y z.w")


@os_agnostic
def test_an_array_of_tables_is_one_value_with_one_source() -> None:
    # The merge records a list as one leaf, so the display shows it as one value.
    lines = _render(_config({"tables": [{"n": 1}, {"n": 2}]}, "tables"))

    _assert_shown_with_source(lines, line="tables = [{n = 1}, {n = 2}]", dotted_key="tables")
    assert "n = 1" not in lines


@os_agnostic
def test_a_none_value_is_shown_as_null_and_the_string_null_stays_a_string() -> None:
    lines = _render(_config({"a": None, "b": "null"}, "a", "b"))

    _assert_shown_with_source(lines, line="a = null", dotted_key="a")
    _assert_shown_with_source(lines, line='b = "null"', dotted_key="b")


@os_agnostic
def test_a_section_view_shows_a_key_toml_must_quote_with_its_source() -> None:
    lines = _render(_config({"probe": {"a b": 1}}, "probe.a b"), section="probe")

    assert "[probe]" in lines
    _assert_shown_with_source(lines, line='"a b" = 1', dotted_key="probe.a b")


@os_agnostic
def test_a_dotted_section_view_shows_the_source_of_its_keys() -> None:
    lines = _render(_config({"deep": {"x": {"y z": {"w": 1}}}}, "deep.x.y z.w"), section="deep.x")

    _assert_shown_with_source(lines, line="w = 1", dotted_key="deep.x.y z.w")
