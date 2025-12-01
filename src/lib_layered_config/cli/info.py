"""Metadata-related CLI commands."""

from __future__ import annotations

import rich_click as click

from ..core import default_env_prefix
from .common import describe_distribution
from .constants import CLICK_CONTEXT_SETTINGS


@click.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def info_command() -> None:
    """Print package metadata in friendly lines."""
    for line in describe_distribution():
        click.echo(line)


@click.command("env-prefix", context_settings=CLICK_CONTEXT_SETTINGS)
@click.argument("slug")
def env_prefix_command(slug: str) -> None:
    """Echo the canonical environment variable prefix for a slug."""
    click.echo(default_env_prefix(slug))


def register(cli_group: click.Group) -> None:
    """Register metadata commands with the root CLI group."""
    cli_group.add_command(info_command)
    cli_group.add_command(env_prefix_command)
