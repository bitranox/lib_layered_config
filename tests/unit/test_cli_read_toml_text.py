"""The ``read`` command prints text that parses back as the TOML it shows.

Its renderer wrote every key bare and every string between plain double quotes, so a key holding
a dot or a space, or a string holding a quote, printed as different or invalid TOML: ``a.b = 3``
under ``[probe]`` reads back as the nested key ``probe.a.b``, and ``[sec tion]`` does not parse.
It now quotes keys, headers and strings the way ``display_config`` does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import rtoml
from click.testing import CliRunner

from lib_layered_config import cli as cli_module
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.support import LayeredSandbox

_TRICKY = """\
quote = "say \\"hi\\" \\\\ back"

[probe]
"a.b" = 3
plain = "x"

[probe."sec tion"]
"" = 1
"k=v" = [1, 2]
"""


def _read_text(sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, document: str) -> str:
    sandbox.apply_env(monkeypatch)
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(document, encoding="utf-8")
    result = CliRunner().invoke(
        cli_module.cli_read_config,
        # --start-dir keeps the .env search inside tmp_path, away from the repository's own .env.
        [
            "--vendor",
            "Acme",
            "--app",
            "Demo",
            "--slug",
            "demo",
            "--default-file",
            str(defaults),
            "--start-dir",
            str(tmp_path),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return result.output


@os_agnostic
def test_the_read_output_parses_back_to_the_configuration(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = _read_text(sandbox, monkeypatch, tmp_path, _TRICKY)

    assert rtoml.loads(output) == rtoml.loads(_TRICKY)


@os_agnostic
def test_a_key_holding_a_dot_is_quoted_not_read_as_nesting(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = _read_text(sandbox, monkeypatch, tmp_path, _TRICKY)

    assert '  "a.b" = 3' in output
    assert '[probe."sec tion"]' in output


@os_agnostic
def test_plain_keys_and_values_print_as_before(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = _read_text(sandbox, monkeypatch, tmp_path, '[service]\nport = 8080\nhost = "localhost"\n')

    assert "\n[service]\n" in output
    assert "  port = 8080" in output
    assert '  host = "localhost"' in output
