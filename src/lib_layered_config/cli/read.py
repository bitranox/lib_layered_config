"""CLI commands related to reading configuration layers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import rich_click as click

from .common import (
    build_read_query,
    human_payload,
    json_payload,
    parse_output_format,
    resolve_indent,
    wants_json,
)
from .constants import CLICK_CONTEXT_SETTINGS
from .typed_click import option


@click.command("read", context_settings=CLICK_CONTEXT_SETTINGS)
@option("--vendor", required=True, help="Vendor namespace")
@option("--app", required=True, help="Application name")
@option("--slug", required=True, help="Slug identifying the configuration set")
@option("--profile", default=None, help="Configuration profile name (e.g., 'test', 'production')")
@option("--prefer", multiple=True, help="Preferred file suffix ordering (repeatable)")
@option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
    help="Starting directory for .env upward search",
)
@option(
    "--default-file",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
    help="Optional lowest-precedence defaults file",
)
@option(
    "--env-file",
    "dotenv_path",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
    help="Explicit .env file path (skips upward directory search)",
)
@option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    show_default=True,
    help="Choose between human prose or JSON",
)
@option(
    "--indent/--no-indent",
    default=True,
    show_default=True,
    help="Pretty-print JSON output",
)
@option(
    "--provenance/--no-provenance",
    default=True,
    show_default=True,
    help="Include provenance metadata in JSON output",
)
@option(
    "--redact/--no-redact",
    default=False,
    show_default=True,
    help="Mask sensitive values (passwords, tokens, keys) in the output",
)
def read_command(
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    prefer: Sequence[str],
    start_dir: Path | None,
    default_file: Path | None,
    dotenv_path: Path | None,
    output_format: str,
    indent: bool,
    provenance: bool,
    redact: bool,
) -> None:
    """Read configuration and print either human prose or JSON."""
    query = build_read_query(vendor, app, slug, profile, prefer, start_dir, default_file, dotenv_path)
    fmt = parse_output_format(output_format)
    if wants_json(fmt):
        click.echo(json_payload(query, resolve_indent(indent), provenance, redact=redact))
        return
    click.echo(human_payload(query, redact=redact))


@click.command("read-json", context_settings=CLICK_CONTEXT_SETTINGS)
@option("--vendor", required=True)
@option("--app", required=True)
@option("--slug", required=True)
@option("--profile", default=None, help="Configuration profile name")
@option("--prefer", multiple=True)
@option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
)
@option(
    "--default-file",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
)
@option(
    "--env-file",
    "dotenv_path",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
    help="Explicit .env file path (skips upward directory search)",
)
@option(
    "--indent/--no-indent",
    default=True,
    show_default=True,
    help="Pretty-print JSON output",
)
@option(
    "--redact/--no-redact",
    default=False,
    show_default=True,
    help="Mask sensitive values (passwords, tokens, keys) in the output",
)
def read_json_command(
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    prefer: Sequence[str],
    start_dir: Path | None,
    default_file: Path | None,
    dotenv_path: Path | None,
    indent: bool,
    redact: bool,
) -> None:
    """Always emit combined JSON (config + provenance)."""
    query = build_read_query(vendor, app, slug, profile, prefer, start_dir, default_file, dotenv_path)
    click.echo(json_payload(query, resolve_indent(indent), include_provenance=True, redact=redact))


def register(cli_group: click.Group) -> None:
    """Register CLI commands defined in this module."""
    cli_group.add_command(read_command)
    cli_group.add_command(read_json_command)
