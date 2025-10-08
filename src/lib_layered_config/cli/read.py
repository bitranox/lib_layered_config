"""CLI commands related to reading configuration layers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import rich_click as click

from .common import (
    build_read_query,
    human_payload,
    json_payload,
    resolve_indent,
    wants_json,
)
from .constants import CLICK_CONTEXT_SETTINGS


@click.command("read", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
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
    prefer: Sequence[str],
    start_dir: Optional[Path],
    default_file: Optional[Path],
    output_format: str,
    indent: bool,
    provenance: bool,
) -> None:
    """Read configuration and print either human prose or JSON."""

    query = build_read_query(vendor, app, slug, prefer, start_dir, default_file)
    if wants_json(output_format):
        click.echo(json_payload(query, resolve_indent(indent), provenance))
        return
    click.echo(human_payload(query))


@click.command("read-json", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True)
@click.option("--app", required=True)
@click.option("--slug", required=True)
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
    prefer: Sequence[str],
    start_dir: Optional[Path],
    default_file: Optional[Path],
    indent: bool,
) -> None:
    """Always emit combined JSON (config + provenance)."""

    query = build_read_query(vendor, app, slug, prefer, start_dir, default_file)
    click.echo(json_payload(query, resolve_indent(indent), include_provenance=True))


def register(cli_group: click.Group) -> None:
    """Register CLI commands defined in this module."""

    cli_group.add_command(read_command)
    cli_group.add_command(read_json_command)
