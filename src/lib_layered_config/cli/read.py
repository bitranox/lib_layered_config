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


@click.command("read", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option("--profile", default=None, help="Configuration profile name (e.g., 'test', 'production')")
@click.option("--prefer", multiple=True, help="Preferred file suffix ordering (repeatable)")
@click.option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
    help="Starting directory for .env upward search",
)
@click.option(
    "--default-file",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
    help="Optional lowest-precedence defaults file",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    show_default=True,
    help="Choose between human prose or JSON",
)
@click.option(
    "--indent/--no-indent",
    default=True,
    show_default=True,
    help="Pretty-print JSON output",
)
@click.option(
    "--provenance/--no-provenance",
    default=True,
    show_default=True,
    help="Include provenance metadata in JSON output",
)
def read_command(
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    prefer: Sequence[str],
    start_dir: Path | None,
    default_file: Path | None,
    output_format: str,
    indent: bool,
    provenance: bool,
) -> None:
    """Read configuration and print either human prose or JSON."""
    query = build_read_query(vendor, app, slug, profile, prefer, start_dir, default_file)
    fmt = parse_output_format(output_format)
    if wants_json(fmt):
        click.echo(json_payload(query, resolve_indent(indent), provenance))
        return
    click.echo(human_payload(query))


@click.command("read-json", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True)
@click.option("--app", required=True)
@click.option("--slug", required=True)
@click.option("--profile", default=None, help="Configuration profile name")
@click.option("--prefer", multiple=True)
@click.option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
)
@click.option(
    "--default-file",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
)
@click.option(
    "--indent/--no-indent",
    default=True,
    show_default=True,
    help="Pretty-print JSON output",
)
def read_json_command(
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    prefer: Sequence[str],
    start_dir: Path | None,
    default_file: Path | None,
    indent: bool,
) -> None:
    """Always emit combined JSON (config + provenance)."""
    query = build_read_query(vendor, app, slug, profile, prefer, start_dir, default_file)
    click.echo(json_payload(query, resolve_indent(indent), include_provenance=True))


def register(cli_group: click.Group) -> None:
    """Register CLI commands defined in this module."""
    cli_group.add_command(read_command)
    cli_group.add_command(read_json_command)
