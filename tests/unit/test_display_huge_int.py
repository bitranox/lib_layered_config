"""A configured int too long to write as decimal text is shown by its width, not raised on.

Python refuses to turn an int of more than 4300 decimal digits into text (``sys.int_info``'s
default ``str_digits_check_threshold``), and a YAML file can carry one, since PyYAML reads a hex
literal without that limit. Both human renderers - ``display_config`` and the ``read`` command -
spelt every scalar with ``str()``, so displaying such a configuration raised ``ValueError:
Exceeds the limit (4300 digits)``. Only YAML reaches it: rtoml refuses an integer wider than 128
bits (about 39 digits), orjson reads a wide integer as a float, and an environment variable stays text.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from lib_layered_config import OutputFormat, display_config, read_config
from lib_layered_config import cli as cli_module
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None

pytestmark = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")

# 4000 hex digits are 16000 bits, about 4817 decimal digits: past the 4300-digit text limit.
_HUGE_HEX = "0x" + "F" * 4000
_HUGE_WIDTH = "<int, 16000 bits>"
_DOCUMENT = f"history:\n  path: {_HUGE_HEX}\n  sizes: [1, {_HUGE_HEX}]\n  small: 42\n"


def _write_defaults(tmp_path: Path) -> Path:
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text(_DOCUMENT, encoding="utf-8")
    return defaults


@os_agnostic
def test_display_config_names_a_huge_int_by_its_width(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.apply_env(monkeypatch)
    # start_dir keeps the .env search inside tmp_path, away from the repository's own .env.
    config = read_config(
        vendor="Acme", app="Demo", slug="demo", default_file=_write_defaults(tmp_path), start_dir=str(tmp_path)
    )

    display_config(config, output_format=OutputFormat.HUMAN)
    output = capsys.readouterr().out

    assert f"path = {_HUGE_WIDTH}" in output
    assert f"sizes = [1, {_HUGE_WIDTH}]" in output
    assert "small = 42" in output


@os_agnostic
def test_the_read_command_names_a_huge_int_by_its_width(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    arguments = ["--vendor", "Acme", "--app", "Demo", "--slug", "demo"]
    arguments += ["--default-file", str(_write_defaults(tmp_path)), "--start-dir", str(tmp_path)]

    result = CliRunner().invoke(cli_module.cli_read_config, arguments, catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert f"  path = {_HUGE_WIDTH}" in result.output
    assert f"  sizes = [1, {_HUGE_WIDTH}]" in result.output
    assert "  small = 42" in result.output
