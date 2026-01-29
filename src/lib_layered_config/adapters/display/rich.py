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

import re
from typing import TYPE_CHECKING

import orjson
import rich_click as click
import rtoml
from rich.console import Console
from rich.text import Text

from ...application.ports import OutputFormat
from ...domain.config import Config
from ...domain.redaction import redact_mapping

if TYPE_CHECKING:
    from ...domain.config import SourceInfo

_REDACTED = "***REDACTED***"
_DEFAULT_CONSOLE = Console(highlight=False)
_OUTPUT_HEADER = r"# Note: Nested dictionaries are displayed as \[section.subsection] headers and might not match the actual TOML \[section]"

# Regex patterns for parsing TOML output
_SECTION_PATTERN = re.compile(r"^\[([^\]]+)\]$")
_KEY_VALUE_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*(.*)$")


def _format_source_line(info: SourceInfo, indent: str = "", *, profile: str | None = None) -> str:
    """Build a source comment string with layer and profile info.

    Args:
        info: Origin metadata dict with ``layer`` and ``path`` keys.
        indent: Leading whitespace before the comment.
        profile: Optional profile name. Displays as ``none`` when not provided.

    Returns:
        A comment string like ``# layer:defaults profile:none (path/to/file.toml)``
        or ``# layer:env profile:none`` when no path is available.
    """
    layer = info["layer"]
    path = info["path"]
    profile_str = profile if profile else "none"

    if path is not None:
        return f"{indent}# layer:{layer} profile:{profile_str} ({path})"
    return f"{indent}# layer:{layer} profile:{profile_str}"


def _render_toml_with_styling(
    toml_text: str,
    config: Config,
    console: Console,
    profile: str | None,
    *,
    section_prefix: str = "",
) -> None:
    """Render TOML text with Rich styling and provenance comments.

    Parses TOML output line by line and applies styling:
    - Section headers [section]: bold cyan
    - Key = value: orange3 key, white =, green value (dim red for redacted)

    Args:
        toml_text: TOML-formatted string from rtoml.dumps().
        config: Config object for provenance lookup.
        console: Rich Console for output.
        profile: Optional profile name for provenance comments.
        section_prefix: Prefix to prepend to section paths for provenance lookup
            (used when displaying a filtered section).
    """
    current_section = section_prefix
    lines = toml_text.split("\n")

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        # Check for section header [section.path]
        section_match = _SECTION_PATTERN.match(stripped)
        if section_match:
            section_path = section_match.group(1)
            current_section = f"{section_prefix}.{section_path}" if section_prefix else section_path
            header = Text(f"\n[{section_path}]")
            header.stylize("bold cyan")
            console.print(header)
            continue

        # Check for key = value
        kv_match = _KEY_VALUE_PATTERN.match(stripped)
        if kv_match:
            key = kv_match.group(1)
            value_str = kv_match.group(2)

            # Build dotted key for provenance lookup
            dotted_key = f"{current_section}.{key}" if current_section else key

            # Print provenance comment if available
            info = config.origin(dotted_key)
            if info is not None:
                indent = "    " if current_section else ""
                console.print(_format_source_line(info, indent, profile=profile), style="yellow")

            # Build styled line
            indent = "    " if current_section else ""
            text = Text(indent)
            text.append(key, style="orange3")
            text.append(" = ", style="white")

            # Check if value is redacted
            if _REDACTED in value_str:
                text.append(value_str, style="dim red")
            else:
                text.append(value_str, style="green")

            console.print(text)
            console.print()


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
        section_data = config.get(section, default=None)
        if section_data is None:
            raise ValueError(f"Section '{section}' not found")
        redacted = redact_mapping({section: section_data})
        click.echo(orjson.dumps(redacted, option=orjson.OPT_INDENT_2).decode())
    else:
        click.echo(config.to_json(indent=2, redact=True))


def _display_human(
    config: Config, section: str | None, *, console: Console | None = None, profile: str | None = None
) -> None:
    """Render configuration as human-readable TOML output to stdout.

    Uses rtoml.dumps() to serialize configuration data to proper TOML format,
    then applies Rich styling for display.
    """
    con = console or _DEFAULT_CONSOLE
    con.print(_OUTPUT_HEADER, style="bright_red")
    con.print()

    if section:
        section_data = config.get(section, default=None)
        if section_data is None:
            raise ValueError(f"Section '{section}' not found")
        redacted_section = redact_mapping({section: section_data})
        redacted_value = redacted_section[section]

        if isinstance(redacted_value, dict):
            # For dict sections, serialize and render with section as prefix
            toml_text = rtoml.dumps({section: redacted_value})
            _render_toml_with_styling(toml_text, config, con, profile)
        else:
            # Scalar value - display directly
            info = config.origin(section)
            if info is not None:
                con.print(_format_source_line(info, "", profile=profile), style="yellow")

            text = Text("")
            text.append(section, style="orange3")
            text.append(" = ", style="white")
            value_str = _format_scalar(redacted_value)
            if redacted_value == _REDACTED:
                text.append(value_str, style="dim red")
            else:
                text.append(value_str, style="green")
            con.print(text)
            con.print()
    else:
        data: dict[str, object] = config.as_dict(redact=True)
        toml_text = rtoml.dumps(data)
        _render_toml_with_styling(toml_text, config, con, profile)


def _format_scalar(value: object) -> str:
    """Format a scalar value as TOML representation.

    Args:
        value: The scalar value to format.

    Returns:
        TOML-formatted string representation.
    """
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return orjson.dumps(value).decode()
    return str(value)


__all__ = [
    "display_config",
]
