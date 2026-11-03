"""Debugging helpers exposed via the CLI."""

from __future__ import annotations

import rich_click as click

from ..testing import i_should_fail
from .constants import CLICK_CONTEXT_SETTINGS
from .envelope import EnvelopeCommand, json_envelope_option, run_in_envelope

__all__ = [
    "fail_command",
    "register",
]


@click.command("fail", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
@json_envelope_option
def fail_command(*, json_envelope: bool) -> None:
    """Intentionally raise a runtime error for test harnesses."""
    if json_envelope:
        run_in_envelope("fail", i_should_fail)
        return
    i_should_fail()


def register(cli_group: click.Group) -> None:
    """Register the fail command with the root CLI group."""
    cli_group.add_command(fail_command)
