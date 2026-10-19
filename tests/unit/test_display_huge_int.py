"""A configured int too long to write as decimal text is shown by its width, not raised on.

Python refuses to turn an int of more than 4300 decimal digits into text (``sys.int_info``'s
default ``str_digits_check_threshold``). Both human renderers - ``display_config`` and the
``read`` command's ``render_human`` - spelt every scalar with ``str()``, so displaying such a
configuration raised ``ValueError: Exceeds the limit (4300 digits)``. The file loaders refuse an
integer outside JSON's range, so such a value now reaches a renderer only in a ``Config`` the
caller built itself; the renderers still must not crash on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_layered_config import Config, OutputFormat, display_config
from lib_layered_config.cli.common import render_human
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    import pytest

# 16000 bits are about 4817 decimal digits: past the 4300-digit text limit.
_HUGE = (1 << 16000) - 1
_HUGE_WIDTH = "<int, 16000 bits>"
_DATA: dict[str, object] = {"history": {"path": _HUGE, "sizes": [1, _HUGE], "small": 42}}


@os_agnostic
def test_display_config_names_a_huge_int_by_its_width(capsys: pytest.CaptureFixture[str]) -> None:
    display_config(Config(_DATA, {}), output_format=OutputFormat.HUMAN)
    output = capsys.readouterr().out

    assert f"path = {_HUGE_WIDTH}" in output
    assert f"sizes = [1, {_HUGE_WIDTH}]" in output
    assert "small = 42" in output


@os_agnostic
def test_the_read_rendering_names_a_huge_int_by_its_width() -> None:
    output = render_human(_DATA, {})

    assert f"  path = {_HUGE_WIDTH}" in output
    assert f"  sizes = [1, {_HUGE_WIDTH}]" in output
    assert "  small = 42" in output
