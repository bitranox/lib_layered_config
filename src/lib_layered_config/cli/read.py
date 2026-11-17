"""CLI commands related to reading configuration layers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import rich_click as click

from ..core import read_config, read_config_raw
from ..domain.redaction import redact_mapping
from .common import (
    build_read_query,
    human_payload,
    json_payload,
    parse_output_format,
    resolve_indent,
    wants_json,
)
from .constants import CLICK_CONTEXT_SETTINGS, OUTPUT_FORMAT_CHOICES
from .envelope import EnvelopeCommand, json_envelope_option, run_in_envelope
from .output import emit_json, emit_text
from .typed_click import option

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .common import ReadQuery


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


def _warn_deprecated_prefer(prefer: Sequence[str]) -> None:
    """Tell the user on stderr that ``--prefer`` does nothing.

    stderr keeps the notice out of a JSON envelope on stdout. The values go no further, so the Python
    API's DeprecationWarning for ``prefer=`` never fires a second time for the same flag.
    """
    if prefer:
        emit_text(_PREFER_WARNING, err=True)


def _envelope_data(query: ReadQuery, *, include_provenance: bool, redact: bool) -> dict[str, object]:
    """Return a read's envelope ``data``: always ``{"config": ..., "provenance": ...}``.

    Without provenance the key stays and holds ``None``. A bare config in ``data`` would make a
    top-level table named ``config`` indistinguishable from the wrapper, and a consumer would have
    to know which flag was passed before it could read the result.

    The data is the mapping ``read_config_json`` and ``Config.to_json`` serialise, built the same
    way, so the envelope's one ``dumps`` writes what the plain JSON output writes.
    """
    if not include_provenance:
        config = read_config(
            vendor=query.vendor,
            app=query.app,
            slug=query.slug,
            profile=query.profile,
            start_dir=query.start_dir,
            default_file=query.default_file,
            dotenv_path=query.dotenv_path,
        )
        return {"config": config.as_dict(redact=redact), "provenance": None}
    result = read_config_raw(
        vendor=query.vendor,
        app=query.app,
        slug=query.slug,
        profile=query.profile,
        start_dir=query.start_dir,
        default_file=query.default_file,
        dotenv_path=query.dotenv_path,
    )
    data = redact_mapping(result.data) if redact else result.data
    return {"config": data, "provenance": result.provenance}


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
    type=click.Choice(OUTPUT_FORMAT_CHOICES, case_sensitive=False),
    default="human",
    show_default=True,
    help="Choose between TOML annotated with each value's source (human) or JSON",
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
    """Read configuration and print it as source-annotated TOML or as JSON."""
    _warn_deprecated_prefer(prefer)
    query = build_read_query(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        start_dir=start_dir,
        default_file=default_file,
        dotenv_path=dotenv_path,
    )
    if json_envelope:
        run_in_envelope(
            "read",
            lambda: _envelope_data(query, include_provenance=provenance, redact=redact),
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
    _warn_deprecated_prefer(prefer)
    query = build_read_query(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        start_dir=start_dir,
        default_file=default_file,
        dotenv_path=dotenv_path,
    )
    if json_envelope:
        run_in_envelope(
            "read-json",
            lambda: _envelope_data(query, include_provenance=True, redact=redact),
        )
        return
    emit_json(json_payload(query, resolve_indent(enabled=indent), include_provenance=True, redact=redact))


def register(cli_group: click.Group) -> None:
    """Register CLI commands defined in this module."""
    cli_group.add_command(read_command)
    cli_group.add_command(read_json_command)
