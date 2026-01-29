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

from typing import cast

import orjson
import rich_click as click
from rich.console import Console
from rich.text import Text

from ...cli.common import OutputFormat
from ...domain.config import Config, SourceInfo
from ...domain.redaction import redact_mapping

_REDACTED = "***REDACTED***"
_SECTION_INDENT = "    "
_TOPLEVEL_INDENT = ""
_DEFAULT_CONSOLE = Console(highlight=False)


def _format_raw_value(value: object) -> str:
    """Format a config value without key prefix.

    Args:
        value: The configuration value to format.

    Returns:
        Formatted string representation of the value.
    """
    if isinstance(value, list):
        return orjson.dumps(value).decode()
    if isinstance(value, str):
        return f'"{value}"'
    return f"{value}"


def _styled_entry(key: str, value: object, *, indent: str = "  ") -> Text:
    """Build a Rich Text object for a styled config key-value line.

    Args:
        key: Configuration key name.
        value: Configuration value.
        indent: Leading whitespace before the key.

    Returns:
        A styled ``Text`` object ready for Console output.
    """
    text = Text(indent)
    text.append(key, style="orange3")
    text.append(" = ", style="white")
    raw = _format_raw_value(value)
    if isinstance(value, str) and value == _REDACTED:
        text.append(raw, style="dim red")
    else:
        text.append(raw, style="green")
    return text


def _format_source_line(info: SourceInfo, indent: str = "  ", *, profile: str | None = None) -> str:
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


def _has_leaf_values(data: dict[str, object]) -> bool:
    """Check if a dict has any non-dict (leaf) values, recursively.

    Args:
        data: Dictionary to check.

    Returns:
        True if any leaf values exist at any nesting level.
    """
    for value in data.values():
        if isinstance(value, dict):
            if _has_leaf_values(cast("dict[str, object]", value)):
                return True
        else:
            return True
    return False


def _print_section(
    section_name: str,
    data: dict[str, object],
    config: Config | None = None,
    *,
    console: Console | None = None,
    profile: str | None = None,
) -> None:
    """Print a configuration section, recursing into nested dicts as TOML sub-sections.

    Args:
        section_name: Dotted section path (e.g. ``lib_log_rich`` or
            ``lib_log_rich.payload_limits``).
        data: Key-value pairs for this section.
        config: Optional Config object for provenance comments. When provided,
            each leaf value is preceded by a ``# layer:`` comment line.
        console: Optional Rich Console for output. Uses module default when None.
        profile: Optional profile name for provenance comments.

    Note:
        Empty sections (dicts with no leaf values) are skipped to avoid
        displaying meaningless headers like ``[section.empty_table]``.
        Leaf values are printed first, then nested subsections, to ensure
        values appear under their correct section header.
    """
    if not _has_leaf_values(data):
        return
    con = console or _DEFAULT_CONSOLE
    header = Text(f"\n[{section_name}]")
    header.stylize("bold cyan")
    con.print(header)
    # First pass: print leaf values (non-dicts) for this section
    for key, value in data.items():
        if not isinstance(value, dict):
            if config is not None:
                dotted_key = f"{section_name}.{key}"
                info = config.origin(dotted_key)
                if info is not None:
                    con.print(_format_source_line(info, _SECTION_INDENT, profile=profile), style="yellow")
            con.print(_styled_entry(key, value, indent=_SECTION_INDENT))
            con.print()
    # Second pass: recurse into nested dicts (subsections)
    for key, value in data.items():
        if isinstance(value, dict):
            _print_section(
                f"{section_name}.{key}", cast("dict[str, object]", value), config, console=con, profile=profile
            )


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
    """Render configuration as human-readable TOML-like output to stdout."""
    con = console or _DEFAULT_CONSOLE
    if section:
        section_data = config.get(section, default=None)
        if section_data is None:
            raise ValueError(f"Section '{section}' not found")
        redacted_section = redact_mapping({section: section_data})
        redacted_value = redacted_section[section]
        if isinstance(redacted_value, dict):
            _print_section(section, cast("dict[str, object]", redacted_value), config, console=con, profile=profile)
        else:
            info = config.origin(section)
            if info is not None:
                con.print(_format_source_line(info, _TOPLEVEL_INDENT, profile=profile), style="yellow")
            con.print(_styled_entry(section, redacted_value, indent=_TOPLEVEL_INDENT))
            con.print()
    else:
        data: dict[str, object] = config.as_dict(redact=True)
        for key, value in data.items():
            if not isinstance(value, dict):
                info = config.origin(key)
                if info is not None:
                    con.print(_format_source_line(info, _TOPLEVEL_INDENT, profile=profile), style="yellow")
                con.print(_styled_entry(key, value, indent=_TOPLEVEL_INDENT))
                con.print()
        for name, value in data.items():
            if isinstance(value, dict):
                _print_section(name, cast("dict[str, object]", value), config, console=con, profile=profile)


__all__ = [
    "display_config",
]
