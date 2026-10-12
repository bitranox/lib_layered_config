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

from dataclasses import dataclass
from typing import TYPE_CHECKING

import orjson
import rich_click as click
from rich.console import Console
from rich.text import Text

from ...application.ports import OutputFormat
from ...domain.redaction import REDACTED_PLACEHOLDER
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
    """What every rendered line needs: the config for provenance, the console, the profile."""

    config: Config
    console: Console
    profile: str | None


def _build_console() -> Console:
    """Build a Rich console that reads the environment at call time.

    ``rich.console.Console`` decides colour support (``_force_terminal``,
    ``_color_system``) once, in ``__init__``, from the environment present at
    that moment. A console built once at import time freezes that decision
    for the process lifetime, so a caller's ``FORCE_COLOR``/``NO_COLOR``
    setting made or changed after import (as every test that pins plain
    output must do) has no effect on it. Building a fresh console per call
    makes the environment at CALL time the one that decides.

    Returns:
        A new ``Console`` with syntax highlighting disabled.
    """
    return Console(highlight=False)


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
    view.console.print()
    info = view.config.origin(".".join(path)) if empty else None
    if info is not None:
        view.console.print(_format_source_line(info, profile=view.profile))
    header = Text("[" + toml_path(path) + "]")
    header.stylize("bold cyan")
    view.console.print(header)


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
            view.console.print(line)


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
        view.console.print(_format_source_line(info, prefix, profile=view.profile))
    if is_array(value):
        _print_overriding_sources(view, key_path=key_path, value=value, prefix=prefix)

    value_str = toml_value(value)
    text = Text(prefix)
    text.append(label, style="orange3")
    text.append(" = ", style="white")
    text.append(value_str, style="dim red" if _REDACTED in value_str else "green")
    view.console.print(text)
    view.console.print()


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
        console: Optional Rich Console for output. When None, uses the module-level
            default. Primarily useful for testing.
        profile: Optional profile name to include in provenance comments.

    Side Effects:
        Writes formatted configuration to stdout via click.echo().

    Raises:
        ValueError: If a section was requested that doesn't exist.

    Note:
        The human-readable format mimics TOML syntax for consistency with the
        configuration file format. JSON format provides machine-readable output
        suitable for parsing by other tools. Sensitive values (passwords,
        secrets, tokens, credentials, API keys) are automatically redacted
        using ``lib_layered_config``'s redaction API.
    """
    if output_format == OutputFormat.JSON:
        _display_json(config, section)
    else:
        _display_human(config, section, console=console, profile=profile)


def _display_json(config: Config, section: str | None) -> None:
    """Render configuration as JSON to stdout."""
    if section:
        if config.get(section, default=_ABSENT) is _ABSENT:
            raise ValueError(f"Section '{section}' not found")
        redacted = {section: config.get_redacted(section)}
        click.echo(orjson.dumps(redacted, option=orjson.OPT_INDENT_2).decode())
    else:
        click.echo(config.to_json(indent=2, redact=True))


def _display_human(
    config: Config, section: str | None, *, console: Console | None = None, profile: str | None = None
) -> None:
    """Render configuration as human-readable TOML output to stdout.

    Walks the redacted mapping itself rather than re-parsing serialised TOML, so every key is shown
    whatever its name and keeps its provenance.
    """
    con = console or _build_console()
    con.print(_OUTPUT_HEADER, style="bright_red")
    con.print()
    view = _View(config, con, profile)

    if not section:
        _render_table(config.as_dict(redact=True), (), view)
        return
    if config.get(section, default=_ABSENT) is _ABSENT:
        raise ValueError(f"Section '{section}' not found")
    redacted_value = config.get_redacted(section)
    if is_table(redacted_value):
        _render_table(redacted_value, tuple(section.split(".")), view)
    else:
        key_path = tuple(section.split("."))
        _print_entry(view, label=toml_path(key_path), key_path=key_path, value=redacted_value, indent=False)


__all__ = [
    "display_config",
]
