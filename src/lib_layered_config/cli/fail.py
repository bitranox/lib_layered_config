"""Debugging helpers exposed via the CLI."""

from __future__ import annotations

import rich_click as click

from ..testing import i_should_fail
from .constants import CLICK_CONTEXT_SETTINGS


@click.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def fail_command() -> None:
    """Intentionally raise a runtime error for test harnesses."""
    i_should_fail()


def register(cli_group: click.Group) -> None:
    """Register the fail command with the root CLI group."""
    cli_group.add_command(fail_command)
