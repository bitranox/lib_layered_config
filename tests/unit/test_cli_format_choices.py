"""``read --format`` offers exactly the OutputFormat members, so the two cannot drift apart."""

from __future__ import annotations

import rich_click as click

from lib_layered_config.application.ports import OutputFormat
from lib_layered_config.cli.read import read_command
from tests.support.os_markers import os_agnostic


@os_agnostic
def test_read_format_choices_are_the_output_format_values() -> None:
    (option,) = [param for param in read_command.params if param.name == "output_format"]
    assert isinstance(option.type, click.Choice)

    assert tuple(option.type.choices) == tuple(member.value for member in OutputFormat)
