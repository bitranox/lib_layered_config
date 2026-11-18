"""Rich-styled configuration display with provenance tracking.

Render configuration data using Rich console styling for enhanced
readability. Supports both human-readable TOML-like output and JSON
format, with automatic redaction of sensitive values.

Contents:
    * :func:`display_config` - Main API for configuration display.
    * Helper functions for formatting and styling individual components.

System Role:
    This module provides the presentation layer for configuration
    visualization. It consumes ``Config`` objects and renders them
    with Rich styling while respecting provenance metadata.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import rich_click as click
from rich.console import Console
from rich.text import Text

from ...application.ports import OutputFormat
from ...domain import json_codec
from ...domain.redaction import REDACTED_PLACEHOLDER
from .._stream_text import fit_json, fitted_console_file
from .toml_text import is_array, is_table, toml_key, toml_path, toml_value

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from ...domain.config import Config, SourceInfo

_REDACTED = REDACTED_PLACEHOLDER
_OUTPUT_HEADER = (
    r"# Note: Nested dictionaries are displayed as \[section.subsection] headers"
    r" and might not match the actual TOML \[section]"
)

# What config.get returns for a missing key, distinct from a key whose value is None.
_ABSENT = object()


@dataclass(frozen=True)
class _View:
    """What every rendered line needs: the config for provenance, the profile, and where lines go.

    Lines are collected and printed in one ``Console.print`` (:func:`_display_human`): Rich's per-call
    pipeline made one print per line cost about 150 us a line. Every collected line is a ``Text``,
    which ``Console.print`` neither highlights nor parses as markup, and none carries a print-level
    style, so joining them with newlines writes the same bytes the separate prints wrote.
    """

    config: Config
    profile: str | None
    lines: list[Text] = field(default_factory=list[Text])

    def emit(self, line: Text | None = None) -> None:
        """Add *line*, or an empty line, to the output."""
        self.lines.append(Text() if line is None else line)


def _build_console() -> Console:
    """Build a Rich console that reads the environment at call time.

    ``rich.console.Console`` decides colour support (``_force_terminal``,
    ``_color_system``) once, in ``__init__``, from the environment present at
    that moment. A console built once at import time freezes that decision
    for the process lifetime, so a caller's ``FORCE_COLOR``/``NO_COLOR``
    setting made or changed after import (as every test that pins plain
    output must do) has no effect on it. Building a fresh console per call
    makes the environment at CALL time the one that decides.

    It writes through a fitting stream (``adapters/_stream_text.py``), so a character stdout
    cannot encode (CJK or an emoji on a cp1252 pipe) is written as a backslash escape instead of
    raising.

    Returns:
        A new ``Console`` with syntax highlighting disabled.
    """
    return Console(file=fitted_console_file(), highlight=False)


def _format_source_line(info: SourceInfo, indent: str = "", *, profile: str | None = None) -> Text:
    """Build the yellow source comment with layer and profile info.

    Returned as ``Text`` rather than ``str`` because Rich parses a printed ``str`` as markup:
    a path is data, and one containing square brackets (a directory named ``cfg[red]x[/red]``)
    would lose them, or raise ``MarkupError`` on an unmatched closing tag.

    Args:
        info: Origin metadata dict with ``layer`` and ``path`` keys.
        indent: Leading whitespace before the comment.
        profile: Optional profile name. Displays as ``none`` when not provided.

    Returns:
        A comment like ``# layer:defaults profile:none (path/to/file.toml)``, or
        ``# layer:env profile:none`` when no path is available.

    Examples:
        >>> _format_source_line({"layer": "user", "path": "/c[red]x[/red]/a.toml", "key": "k"}).plain
        '# layer:user profile:none (/c[red]x[/red]/a.toml)'
    """
    layer = info["layer"]
    path = info["path"]
    profile_str = profile if profile else "none"

    line = f"{indent}# layer:{layer} profile:{profile_str}"
    if path is not None:
        line = f"{line} ({path})"
    return Text(line, style="yellow")


def _render_table(table: Mapping[str, object], path: tuple[str, ...], view: _View) -> None:
    """Print *table*'s own keys under its ``[header]``, then each sub-table the same way.

    The walk reads the mapping itself, so a key is shown whatever its name, and its provenance is
    looked up under the raw names joined by dots - the way the merge records it.
    """
    leaves = [(key, value) for key, value in table.items() if not is_table(value)]
    tables = [(key, value) for key, value in table.items() if is_table(value)]
    # Like TOML, a table that holds only sub-tables needs no header of its own.
    if path and (leaves or not tables):
        _render_header(path, view, empty=not table)
    for key, value in leaves:
        _render_key_value(key, value, path, view)
    for key, value in tables:
        if is_table(value):
            _render_table(value, (*path, key), view)


def _render_header(path: tuple[str, ...], view: _View, *, empty: bool) -> None:
    """Print a table's ``[header]`` (bold cyan); an empty table carries its own source."""
    view.emit()
    info = view.config.origin(".".join(path)) if empty else None
    if info is not None:
        view.emit(_format_source_line(info, profile=view.profile))
    header = Text("[" + toml_path(path) + "]")
    header.stylize("bold cyan")
    view.emit(header)


def _element_paths(value: object, path: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    """Yield the path of every element and member below a list value, depth first."""
    if is_array(value):
        children: list[tuple[str, object]] = [(str(index), item) for index, item in enumerate(value)]
    elif is_table(value):
        children = list(value.items())
    else:
        return
    for name, child in children:
        yield (*path, name)
        yield from _element_paths(child, (*path, name))


def _print_overriding_sources(view: _View, *, key_path: tuple[str, ...], value: object, prefix: str) -> None:
    """Print the source of every list element a different layer set (an indexed override).

    The merge records a list under its own key, and an element a higher layer replaced by index
    (``APP___HOSTS__0__NAME``) under that element's path, so the list's own source alone would
    name the wrong layer for it.
    """
    own = view.config.origin(".".join(key_path))
    for element in _element_paths(value, key_path):
        info = view.config.origin(".".join(element))
        if info is not None and not _same_source(info, own):
            line = _format_source_line(info, prefix, profile=view.profile)
            line.append(f" for {toml_path(element)}")
            view.emit(line)


def _same_source(info: SourceInfo, other: SourceInfo | None) -> bool:
    """Return whether two provenance entries name the same layer and file (their keys differ)."""
    return other is not None and (info["layer"], info["path"]) == (other["layer"], other["path"])


def _render_key_value(key: str, value: object, path: tuple[str, ...], view: _View) -> None:
    """Print the ``key = value`` line of *key* in the table at *path*."""
    _print_entry(view, label=toml_key(key), key_path=(*path, key), value=value, indent=bool(path))


def _print_entry(view: _View, *, label: str, key_path: tuple[str, ...], value: object, indent: bool) -> None:
    """Print one ``label = value`` line with its provenance comment and value styling."""
    prefix = "    " if indent else ""
    info = view.config.origin(".".join(key_path))
    if info is not None:
        view.emit(_format_source_line(info, prefix, profile=view.profile))
    if is_array(value):
        _print_overriding_sources(view, key_path=key_path, value=value, prefix=prefix)

    value_str = toml_value(value)
    text = Text(prefix)
    text.append(label, style="orange3")
    text.append(" = ", style="white")
    text.append(value_str, style="dim red" if _REDACTED in value_str else "green")
    view.emit(text)
    view.emit()


def display_config(
    config: Config,
    *,
    output_format: OutputFormat = OutputFormat.HUMAN,
    section: str | None = None,
    console: Console | None = None,
    profile: str | None = None,
) -> None:
    """Display the provided configuration in the requested format.

    Users need visibility into the effective configuration loaded from
    defaults, app configs, host configs, user configs, .env files, and
    environment variables. Outputs the provided Config object in the
    requested format.

    Args:
        config: Already-loaded layered configuration object to display.
        output_format: Output format: OutputFormat.HUMAN for TOML-like display or
            OutputFormat.JSON for JSON. Defaults to OutputFormat.HUMAN.
        section: Optional section name to display only that section. When None,
            displays all configuration.
        console: Optional Rich Console for the human format. When None, a console on stdout
            that writes a character stdout cannot encode as a backslash escape. A console you
            pass writes to its own file as it is, so it raises where that file cannot encode.
        profile: Optional profile name to include in provenance comments.

    Side Effects:
        Writes formatted configuration to stdout. A character stdout cannot encode (CJK or an
        emoji on a Windows cp1252 pipe) is written as an escape instead of raising: ``\\uXXXX``
        in JSON, which parses back to the same value, and a Python backslash escape in the human
        format, as the CLI's ``read`` does. The human format prints its note line, then the whole
        body in one ``Console.print``, so the output appears when the call finishes.

    Raises:
        ValueError: If a section was requested that doesn't exist, or *output_format* is not one
            of the :class:`OutputFormat` values.

    Note:
        The human-readable format mimics TOML syntax for consistency with the
        configuration file format. JSON format provides machine-readable output
        suitable for parsing by other tools. Sensitive values (passwords,
        secrets, tokens, credentials, API keys) are automatically redacted
        using ``lib_layered_config``'s redaction API.

    Examples:
        >>> from lib_layered_config import Config
        >>> config = Config({"db": {"host": "localhost", "password": "hunter2"}}, {})
        >>> display_config(config, output_format=OutputFormat.JSON)
        {
          "db": {
            "host": "localhost",
            "password": "***REDACTED***"
          }
        }
    """
    if _known_format(output_format) is OutputFormat.JSON:
        _display_json(config, section)
    else:
        _display_human(config, section, console=console, profile=profile)


def _known_format(output_format: OutputFormat) -> OutputFormat:
    """Return *output_format* as an :class:`OutputFormat`, refusing any other value.

    An untyped caller can pass the format's text. A value that names no format is refused so a
    typo fails instead of falling through to the human view.
    """
    try:
        return OutputFormat(output_format)
    except ValueError:
        choices = ", ".join(repr(member.value) for member in OutputFormat)
        raise ValueError(f"output_format must be one of {choices}, not {output_format!r}") from None


def _display_json(config: Config, section: str | None) -> None:
    """Render configuration as JSON to stdout."""
    if section:
        # One read answers both "is it there" and "what does it show": a separate presence check copied the section too.
        section_value = config.get_redacted(section, _ABSENT)
        if section_value is _ABSENT:
            raise ValueError(f"Section '{section}' not found")
        redacted = {section: section_value}
        click.echo(fit_json(json_codec.dumps(redacted, indent=True), sys.stdout))
    else:
        click.echo(fit_json(config.to_json(indent=2, redact=True), sys.stdout))


def _display_human(
    config: Config, section: str | None, *, console: Console | None = None, profile: str | None = None
) -> None:
    """Render configuration as human-readable TOML output to stdout.

    Walks the redacted mapping itself rather than re-parsing serialised TOML, so every key is shown
    whatever its name and keeps its provenance.
    """
    # The section is looked up before anything is printed, so a missing one leaves the output empty, as the
    # JSON format does, instead of a header followed by an error.
    redacted_value = config.get_redacted(section, _ABSENT) if section else _ABSENT
    if section and redacted_value is _ABSENT:
        raise ValueError(f"Section '{section}' not found")
    con = console or _build_console()
    # soft_wrap on every print, a caller's console included: Rich otherwise breaks each line at the
    # console width (80 on a pipe), and a broken comment or string no longer reads back as TOML.
    # The note is a str printed with a print-level style, which also styles its line ending and is
    # highlighted when the console highlights, so it is printed on its own to keep those bytes.
    con.print(_OUTPUT_HEADER, style="bright_red", soft_wrap=True)
    con.print(soft_wrap=True)
    view = _View(config, profile)

    if not section:
        _render_table(config.as_dict(redact=True), (), view)
    elif is_table(redacted_value):
        _render_table(redacted_value, tuple(section.split(".")), view)
    else:
        key_path = tuple(section.split("."))
        _print_entry(view, label=toml_path(key_path), key_path=key_path, value=redacted_value, indent=False)
    if view.lines:
        con.print(Text("\n").join(view.lines), soft_wrap=True)


__all__ = [
    "display_config",
]
