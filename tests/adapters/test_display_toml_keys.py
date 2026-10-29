"""The human display shows every key, whatever its name, with the provenance of its value.

The display used to serialise the configuration to TOML and re-parse that text line by line, so
every line its two patterns did not expect vanished: a key TOML must quote (a space, a dot, a
non-ASCII letter, the empty name), an array of tables, and the provenance of any key under a
quoted section name. Each case below is a shape a configuration file can legitimately hold.
"""

from __future__ import annotations

import datetime
import io
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from lib_layered_config import Config, OutputFormat, display_config
from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer
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
        pytest.param("1st", "1st", id="leading-digit"),
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


# --- shapes the real merge produces -----------------------------------------------------------


def _merged(*layers: tuple[Layer, dict[str, Any], str | None]) -> Config:
    result = merge_layers([LayerSnapshot(name, payload, origin) for name, payload, origin in layers])
    return Config(result.data, result.provenance)


@os_agnostic
def test_a_list_element_a_higher_layer_overrode_names_that_layer_too() -> None:
    # An indexed override (APP___HOSTS__0__NAME=x) records hosts.0.name, not hosts.
    config = _merged(
        (Layer.DEFAULTS, {"hosts": [{"name": "a"}, {"name": "b"}]}, "/etc/app/defaults.toml"),
        (Layer.ENV, {"hosts": {"0": {"name": "x"}}}, None),
    )

    lines = _render(config)

    shown = lines.index('hosts = [{name = "x"}, {name = "b"}]')
    assert lines[shown - 2] == "# layer:defaults profile:none (/etc/app/defaults.toml)"
    assert lines[shown - 1] == "# layer:env profile:none for hosts.0.name"


@os_agnostic
def test_an_empty_table_shows_its_source_above_its_header() -> None:
    config = _merged((Layer.DEFAULTS, {"styles": {}}, "/etc/app/defaults.toml"))

    lines = _render(config)

    assert lines[lines.index("[styles]") - 1] == "# layer:defaults profile:none (/etc/app/defaults.toml)"


@os_agnostic
def test_a_table_shows_its_own_keys_before_its_sub_tables() -> None:
    lines = _render(_config({"t": {"sub": {"x": 1}, "leaf": 2}}))

    assert lines.index("leaf = 2") < lines.index("[t.sub]")


@os_agnostic
def test_a_none_value_can_be_shown_on_its_own() -> None:
    lines = _render(_config({"a": None}, "a"), section="a")

    _assert_shown_with_source(lines, line="a = null", dotted_key="a")


@os_agnostic
def test_a_c1_control_character_never_reaches_the_terminal() -> None:
    # U+009B is CSI, which a terminal reads as the start of an escape sequence.
    lines = _render(_config({"k": "a\u009bb", "\u009b": 1}))

    assert r'k = "a\u009bb"' in lines
    assert r'"\u009b" = 1' in lines
    assert not any("\u009b" in line for line in lines)


@os_agnostic
def test_a_scalar_section_label_is_quoted_like_any_key() -> None:
    lines = _render(_config({"a b": 1}, "a b"), section="a b")

    _assert_shown_with_source(lines, line='"a b" = 1', dotted_key="a b")


@os_agnostic
def test_a_set_is_shown_as_a_sorted_array() -> None:
    lines = _render(_config({"s": {"b", "a"}}))

    assert 's = ["a", "b"]' in lines


@os_agnostic
def test_a_utc_datetime_ends_in_z_as_toml_writes_it() -> None:
    lines = _render(_config({"t": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)}))

    assert "t = 2026-01-01T00:00:00Z" in lines


@os_agnostic
def test_an_override_from_the_list_s_own_source_adds_no_line() -> None:
    config = _merged(
        (Layer.ENV, {"h": [{"n": "a"}, {"n": "b"}]}, None),
        (Layer.ENV, {"h": {"0": {"n": "x"}}}, None),
    )

    lines = _render(config)

    assert [line for line in lines if line.startswith("# layer:")] == ["# layer:env profile:none"]


@os_agnostic
def test_an_override_under_a_dotted_key_names_its_path_quoted() -> None:
    config = _merged(
        (Layer.DEFAULTS, {"a.b": [{"n": "a"}]}, "/etc/app/defaults.toml"),
        (Layer.ENV, {"a.b": {"0": {"n": "x"}}}, None),
    )

    lines = _render(config)

    assert '# layer:env profile:none for "a.b".0.n' in lines
