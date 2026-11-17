"""``display_config``'s human format writes exactly the bytes the per-line printing wrote.

The human view used to call ``Console.print`` once per line (three calls per leaf), and Rich's
per-call pipeline made it 75-90x slower than the JSON view. It now prints once per call. This test
keeps the per-line printer as the oracle (``_PerLineOracle``, the renderer as it stood before that
change, built from the same public helpers) and requires byte-identical output from both under every
console setting a caller can pass: highlighting on and off, no colour, forced truecolor, forced
standard colour, widths 40, 80 and 200, for the whole configuration and for a section. Both arms run
in one process against the same Rich, so a Rich upgrade cannot fail it by itself.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pytest
from rich.console import Console
from rich.text import Text

from lib_layered_config import Config, display_config
from lib_layered_config.adapters.display.toml_text import is_array, is_table, toml_key, toml_path, toml_value
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from lib_layered_config.domain.config import SourceInfo

_NOTE = (
    r"# Note: Nested dictionaries are displayed as \[section.subsection] headers"
    r" and might not match the actual TOML \[section]"
)
_ABSENT = object()

ColorSystem = Literal["standard", "truecolor"] | None


def _source(layer: str, key: str, path: str | None = "/etc/acme/config.toml") -> SourceInfo:
    return {"layer": layer, "path": path, "key": key}


def _config() -> Config:
    """A configuration exercising every line kind the human view prints."""
    data: dict[str, object] = {
        "debug": True,
        "name": "a long application name that wraps at forty columns and keeps going",
        "db": {
            "host": "db.example.com",
            "port": 5432,
            "password": "hunter2",
            "replicas": ["r1.example.com", "r2.example.com", "r3.example.com"],
            "options": {"timeout": 1.5, "retry": [1, 2, {"backoff": "exp"}]},
        },
        "styles": {},
        "odd thing.name": {"[red]markup[/red]": "value with [brackets] and 'quotes' 12 True None 1.0e3"},
    }
    meta = {
        "debug": _source("env", "debug", None),
        "name": _source("defaults", "name", "/opt/app/c[red]x[/red]/defaults.toml"),
        "db.host": _source("app", "db.host"),
        "db.port": _source("host", "db.port", "/etc/acme/hosts/box.toml"),
        "db.password": _source("dotenv", "db.password", "/srv/project/.env"),
        "db.replicas": _source("app", "db.replicas"),
        "db.replicas.1": _source("env", "db.replicas.1", None),
        "db.options.timeout": _source("user", "db.options.timeout", "/home/u/.config/acme/config.toml"),
        "db.options.retry": _source("app", "db.options.retry"),
        "db.options.retry.2.backoff": _source("override", "db.options.retry.2.backoff", None),
        "styles": _source("defaults", "styles", "/opt/app/defaults.toml"),
        "odd thing.name.[red]markup[/red]": _source("cli", "odd thing.name.[red]markup[/red]", None),
    }
    return Config(data, meta)


@dataclass(frozen=True)
class _PerLineOracle:
    """The human renderer as it was: one ``Console.print`` per line."""

    config: Config
    console: Console
    profile: str | None

    def render(self, section: str | None) -> None:
        value = self.config.get_redacted(section, _ABSENT) if section else _ABSENT
        self.console.print(_NOTE, style="bright_red")
        self.console.print()
        if not section:
            self._table(self.config.as_dict(redact=True), ())
        elif is_table(value):
            self._table(value, tuple(section.split(".")))
        else:
            path = tuple(section.split("."))
            self._entry(label=toml_path(path), key_path=path, value=value, indent=False)

    def _source_line(self, info: SourceInfo, indent: str = "") -> Text:
        line = f"{indent}# layer:{info['layer']} profile:{self.profile or 'none'}"
        if info["path"] is not None:
            line = f"{line} ({info['path']})"
        return Text(line, style="yellow")

    def _table(self, table: Mapping[str, object], path: tuple[str, ...]) -> None:
        leaves = [(key, value) for key, value in table.items() if not is_table(value)]
        tables = [(key, value) for key, value in table.items() if is_table(value)]
        if path and (leaves or not tables):
            self._header(path, empty=not table)
        for key, value in leaves:
            self._entry(label=toml_key(key), key_path=(*path, key), value=value, indent=bool(path))
        for key, value in tables:
            if is_table(value):
                self._table(value, (*path, key))

    def _header(self, path: tuple[str, ...], *, empty: bool) -> None:
        self.console.print()
        info = self.config.origin(".".join(path)) if empty else None
        if info is not None:
            self.console.print(self._source_line(info))
        header = Text("[" + toml_path(path) + "]")
        header.stylize("bold cyan")
        self.console.print(header)

    def _entry(self, *, label: str, key_path: tuple[str, ...], value: object, indent: bool) -> None:
        prefix = "    " if indent else ""
        info = self.config.origin(".".join(key_path))
        if info is not None:
            self.console.print(self._source_line(info, prefix))
        if is_array(value):
            own = self.config.origin(".".join(key_path))
            for element in _element_paths(value, key_path):
                other = self.config.origin(".".join(element))
                if other is not None and (
                    own is None or (other["layer"], other["path"]) != (own["layer"], own["path"])
                ):
                    line = self._source_line(other, prefix)
                    line.append(f" for {toml_path(element)}")
                    self.console.print(line)
        value_str = toml_value(value)
        text = Text(prefix)
        text.append(label, style="orange3")
        text.append(" = ", style="white")
        text.append(value_str, style="dim red" if REDACTED_PLACEHOLDER in value_str else "green")
        self.console.print(text)
        self.console.print()


def _element_paths(value: object, path: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    if is_array(value):
        children: list[tuple[str, object]] = [(str(index), item) for index, item in enumerate(value)]
    elif is_table(value):
        children = list(value.items())
    else:
        return
    for name, child in children:
        yield (*path, name)
        yield from _element_paths(child, (*path, name))


def _console(buffer: io.StringIO, *, highlight: bool, color_system: ColorSystem, width: int) -> Console:
    # An empty environment: NO_COLOR (set by some harnesses) would strip every colour from BOTH arms
    # and hide a lost style, as it hid one that dropped the note's red.
    return Console(
        file=buffer,
        highlight=highlight,
        color_system=color_system,
        force_terminal=color_system is not None,
        width=width,
        _environ={},
    )


@os_agnostic
@pytest.mark.parametrize("section", [None, "db", "db.options", "debug", "db.replicas", "db.password", "styles"])
@pytest.mark.parametrize("width", [40, 80, 200])
@pytest.mark.parametrize("color_system", [None, "truecolor", "standard"])
@pytest.mark.parametrize("highlight", [False, True])
def test_the_human_view_writes_the_bytes_the_per_line_printer_wrote(
    highlight: bool, color_system: ColorSystem, width: int, section: str | None
) -> None:
    config = _config()
    expected, actual = io.StringIO(), io.StringIO()

    _PerLineOracle(
        config, _console(expected, highlight=highlight, color_system=color_system, width=width), "prod"
    ).render(section)
    display_config(
        config,
        section=section,
        console=_console(actual, highlight=highlight, color_system=color_system, width=width),
        profile="prod",
    )

    assert actual.getvalue() == expected.getvalue()


@os_agnostic
def test_the_oracle_sees_colour_and_highlighting_so_the_comparison_can_fail() -> None:
    """A control: the settings above produce different bytes, so equal output is not vacuous."""
    plain, coloured, highlighted = io.StringIO(), io.StringIO(), io.StringIO()
    config = _config()

    _PerLineOracle(config, _console(plain, highlight=False, color_system=None, width=80), None).render(None)
    _PerLineOracle(config, _console(coloured, highlight=False, color_system="truecolor", width=80), None).render(None)
    _PerLineOracle(config, _console(highlighted, highlight=True, color_system="truecolor", width=80), None).render(None)

    assert len({plain.getvalue(), coloured.getvalue(), highlighted.getvalue()}) == 3
    assert "\x1b[" not in plain.getvalue()
    # The note's bright red and a value's green reach the bytes, with and without highlighting.
    assert coloured.getvalue().startswith("\x1b[91m# Note:")
    assert "\x1b[91m# Note:" in highlighted.getvalue()
    assert "\x1b[32m" in coloured.getvalue()
