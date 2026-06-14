"""CLI command for generating example configuration trees."""

from __future__ import annotations

from pathlib import Path

import rich_click as click

from ..examples import generate_examples as generate_examples_impl
from .common import json_paths, normalise_examples_platform_option
from .constants import CLICK_CONTEXT_SETTINGS
from .typed_click import option


@click.command("generate-examples", context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--destination",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, resolve_path=True),
    required=True,
    help="Directory that will receive the example tree",
)
@option("--slug", required=True, help="Slug identifying the configuration set")
@option("--vendor", required=True, help="Vendor namespace")
@option("--app", required=True, help="Application name")
@option(
    "--platform",
    default=None,
    help="Override platform layout (posix/windows)",
)
@option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Overwrite existing example files",
)
def generate_examples_command(
    destination: Path,
    slug: str,
    vendor: str,
    app: str,
    platform: str | None,
    force: bool,
) -> None:
    """Create reference example trees for documentation or onboarding."""
    created = generate_examples_impl(
        destination,
        slug=slug,
        vendor=vendor,
        app=app,
        force=force,
        platform=normalise_examples_platform_option(platform),
    )
    click.echo(json_paths(created))


def register(cli_group: click.Group) -> None:
    """Register the generate-examples command."""
    cli_group.add_command(generate_examples_command)
