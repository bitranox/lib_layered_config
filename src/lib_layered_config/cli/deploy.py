"""CLI command for deploying configuration files into layer directories."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import rich_click as click

from ..examples import deploy_config as deploy_config_impl
from .common import json_paths, normalise_platform_option, normalise_targets
from .constants import CLICK_CONTEXT_SETTINGS, TARGET_CHOICES


@click.command("deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--source",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    required=True,
    help="Path to the configuration file that should be copied",
)
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option(
    "--target",
    "targets",
    multiple=True,
    required=True,
    type=click.Choice(TARGET_CHOICES, case_sensitive=False),
    help="Layer targets to deploy to (repeatable)",
)
@click.option(
    "--platform",
    default=None,
    help="Override auto-detected platform (linux, darwin, windows)",
)
@click.option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Overwrite existing files at the destination",
)
def deploy_command(
    source: Path,
    vendor: str,
    app: str,
    slug: str,
    targets: Sequence[str],
    platform: Optional[str],
    force: bool,
) -> None:
    """Copy a source file into the requested layered directories."""

    created = deploy_config_impl(
        source,
        vendor=vendor,
        app=app,
        slug=slug,
        targets=normalise_targets(targets),
        platform=normalise_platform_option(platform),
        force=force,
    )
    click.echo(json_paths(created))


def register(cli_group: click.Group) -> None:
    """Register the deploy command with the root CLI group."""

    cli_group.add_command(deploy_command)
