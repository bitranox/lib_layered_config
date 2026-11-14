"""CLI commands related to reading configuration layers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import rich_click as click

from ..domain import json_codec
from .common import (
    build_read_query,
    human_payload,
    json_payload,
    parse_output_format,
    resolve_indent,
    wants_json,
)
from .constants import CLICK_CONTEXT_SETTINGS
from .envelope import EnvelopeCommand, json_envelope_option, run_in_envelope
from .output import emit_json, emit_text
from .typed_click import option

if TYPE_CHECKING:
    from collections.abc import Sequence


__all__ = [
    "read_command",
    "read_json_command",
    "register",
]

_PREFER_HELP = "Deprecated, no effect: each layer reads config.toml and config.d/ (repeatable)"
_PREFER_WARNING = (
    "warning: --prefer has no effect and will be removed in a future major release: each layer "
    "reads only config.toml and its config.d/ directory, which is where JSON and YAML files go"
)


def _drop_deprecated_prefer(prefer: Sequence[str]) -> tuple[str, ...]:
    """Tell the user on stderr that ``--prefer`` does nothing, and return no suffixes.

    stderr keeps the notice out of a JSON envelope on stdout, and the empty result keeps the Python
    API from warning a second time about the same flag.
    """
    if prefer:
        emit_text(_PREFER_WARNING, err=True)
    return ()


@click.command("read", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
@option("--vendor", required=True, help="Vendor namespace")
@option("--app", required=True, help="Application name")
@option("--slug", required=True, help="Slug identifying the configuration set")
@option("--profile", default=None, help="Configuration profile name (e.g., 'test', 'production')")
@option("--prefer", multiple=True, help=_PREFER_HELP)
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
    default=True,
    show_default=True,
    help="Mask sensitive values (passwords, tokens, keys) in the output; --no-redact prints them",
)
@json_envelope_option
def read_command(
    *,
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
    json_envelope: bool,
) -> None:
    """Read configuration and print either human prose or JSON."""
    query = build_read_query(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        prefer=_drop_deprecated_prefer(prefer),
        start_dir=start_dir,
        default_file=default_file,
        dotenv_path=dotenv_path,
    )
    if json_envelope:
        run_in_envelope(
            "read",
            lambda: json_codec.loads(json_payload(query, None, include_provenance=provenance, redact=redact)),
        )
        return
    fmt = parse_output_format(output_format)
    if wants_json(fmt):
        emit_json(json_payload(query, resolve_indent(enabled=indent), include_provenance=provenance, redact=redact))
        return
    emit_text(human_payload(query, redact=redact))


@click.command("read-json", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
@option("--vendor", required=True)
@option("--app", required=True)
@option("--slug", required=True)
@option("--profile", default=None, help="Configuration profile name")
@option("--prefer", multiple=True, help=_PREFER_HELP)
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
    default=True,
    show_default=True,
    help="Mask sensitive values (passwords, tokens, keys) in the output; --no-redact prints them",
)
@json_envelope_option
def read_json_command(
    *,
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
    json_envelope: bool,
) -> None:
    """Always emit combined JSON (config + provenance)."""
    query = build_read_query(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        prefer=_drop_deprecated_prefer(prefer),
        start_dir=start_dir,
        default_file=default_file,
        dotenv_path=dotenv_path,
    )
    if json_envelope:
        run_in_envelope(
            "read-json",
            lambda: json_codec.loads(json_payload(query, None, include_provenance=True, redact=redact)),
        )
        return
    emit_json(json_payload(query, resolve_indent(enabled=indent), include_provenance=True, redact=redact))


def register(cli_group: click.Group) -> None:
    """Register CLI commands defined in this module."""
    cli_group.add_command(read_command)
    cli_group.add_command(read_json_command)
