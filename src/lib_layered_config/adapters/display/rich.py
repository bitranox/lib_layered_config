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

import datetime
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard

import orjson
import rich_click as click
from rich.console import Console
from rich.text import Text

from ...application.ports import OutputFormat
from ...domain.redaction import REDACTED_PLACEHOLDER

if TYPE_CHECKING:
    from ...domain.config import Config, SourceInfo

_REDACTED = REDACTED_PLACEHOLDER
_OUTPUT_HEADER = (
    r"# Note: Nested dictionaries are displayed as \[section.subsection] headers"
    r" and might not match the actual TOML \[section]"
)

# A key TOML can write without quotes; any other key is shown as a quoted string.
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


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


def _is_table(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_array(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _toml_string(text: str) -> str:
    r"""Return *text* as a TOML basic string, escaping quotes and every control character.

    Examples:
        >>> _toml_string('say "hi"\x1b')
        '"say \\"hi\\"\\u001b"'
    """
    # A JSON string is a TOML basic string, except that TOML also forbids a raw DEL.
    return orjson.dumps(text).decode().replace("\x7f", "\\u007f")


def _toml_key(key: str) -> str:
    """Return *key* as TOML writes it: bare when it can be, quoted otherwise.

    Examples:
        >>> _toml_key("db_host"), _toml_key("a b"), _toml_key("")
        ('db_host', '"a b"', '""')
    """
    return key if _BARE_KEY.fullmatch(key) else _toml_string(key)


def _toml_value(value: object) -> str:
    """Return *value* in TOML inline syntax; ``None``, which TOML cannot hold, shows as ``null``.

    Examples:
        >>> _toml_value([{"n": 1}, None, "x"])
        '[{n = 1}, null, "x"]'
    """
    if _is_table(value):
        return "{" + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items()) + "}"
    if _is_array(value):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return _toml_scalar(value)


def _toml_scalar(value: object) -> str:
    """Return a scalar in TOML syntax (``null`` for ``None``)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, float) and not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


def _render_table(table: Mapping[str, object], path: tuple[str, ...], view: _View) -> None:
    """Print *table*'s own keys under its ``[header]``, then each sub-table the same way.

    The walk reads the mapping itself, so a key is shown whatever its name, and its provenance is
    looked up under the raw names joined by dots - the way the merge records it.
    """
    leaves = [(key, value) for key, value in table.items() if not _is_table(value)]
    tables = [(key, value) for key, value in table.items() if _is_table(value)]
    # Like TOML, a table that holds only sub-tables needs no header of its own.
    if path and (leaves or not tables):
        header = Text("\n[" + ".".join(_toml_key(part) for part in path) + "]")
        header.stylize("bold cyan")
        view.console.print(header)
    for key, value in leaves:
        _render_key_value(key, value, path, view)
    for key, value in tables:
        if _is_table(value):
            _render_table(value, (*path, key), view)


def _render_key_value(key: str, value: object, path: tuple[str, ...], view: _View) -> None:
    """Print the ``key = value`` line of *key* in the table at *path*."""
    _print_entry(view, label=_toml_key(key), dotted_key=".".join((*path, key)), value=value, indent=bool(path))


def _print_entry(view: _View, *, label: str, dotted_key: str, value: object, indent: bool) -> None:
    """Print one ``label = value`` line with its provenance comment and value styling."""
    prefix = "    " if indent else ""
    info = view.config.origin(dotted_key)
    if info is not None:
        view.console.print(_format_source_line(info, prefix, profile=view.profile))

    value_str = _toml_value(value)
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
        if config.get(section, default=None) is None:
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
    if config.get(section, default=None) is None:
        raise ValueError(f"Section '{section}' not found")
    redacted_value = config.get_redacted(section)
    if _is_table(redacted_value):
        _render_table(redacted_value, tuple(section.split(".")), view)
    else:
        _print_entry(view, label=section, dotted_key=section, value=redacted_value, indent=False)


__all__ = [
    "display_config",
]
