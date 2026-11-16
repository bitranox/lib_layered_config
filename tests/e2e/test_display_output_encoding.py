"""``display_config`` never fails because stdout cannot encode a configuration value.

A piped stdout on Windows uses the ANSI code page (cp1252 on a German or English install), which
has no CJK characters and no emoji, and ``display_config`` raised ``UnicodeEncodeError`` there: the
JSON view printed nothing, the human view stopped part-way. User decision 2026-11-16 (R4-F1, "Same
rule as the CLI"): it fits its output to the stream the way the CLI's ``read`` does, a ``\\uXXXX``
escape in JSON and a Python backslash escape in the human view, and a character the stream can
encode is written as it is. The display runs in a child process because the stream encoding is the
child's own (``PYTHONIOENCODING``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_KANJI = chr(0x6F22)
_EMOJI = chr(0x1F600)
_UMLAUT = chr(0xFC)
_VALUE = f"{_UMLAUT}-{_KANJI}-{_EMOJI}"
_B = chr(92)

#: Reads the sandbox's config and displays it; argv: output format, start dir, section ("" for none).
_DISPLAY = """
import sys
from lib_layered_config import display_config, read_config
from lib_layered_config.application.ports import OutputFormat
config = read_config(vendor="Acme", app="EncodeKit", slug="encode-kit", start_dir=sys.argv[2])
display_config(config, output_format=OutputFormat(sys.argv[1]), section=sys.argv[3] or None)
"""


@pytest.fixture
def sandbox(tmp_path: Path) -> LayeredSandbox:
    box = create_layered_sandbox(tmp_path, vendor="Acme", app="EncodeKit", slug="encode-kit")
    box.write("user", "config.toml", content=f'[a]\nname = "{_VALUE}"\n')
    return box


def _display(
    sandbox: LayeredSandbox, cwd: Path, *, output_format: str, section: str, encoding: str
) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, **sandbox.env, "NO_COLOR": "1", "PYTHONIOENCODING": encoding}
    env.pop("FORCE_COLOR", None)
    return subprocess.run(  # noqa: S603 - argv is this interpreter, a fixed script and fixed arguments, no shell
        [sys.executable, "-c", _DISPLAY, output_format, str(cwd), section],
        capture_output=True,
        env=env,
        cwd=str(cwd),
        timeout=120,
        check=False,
    )


@os_agnostic
@pytest.mark.parametrize("section", ["", "a"], ids=["whole", "section"])
def test_the_json_view_on_a_cp1252_stdout_parses_back_to_the_exact_value(
    sandbox: LayeredSandbox, tmp_path: Path, section: str
) -> None:
    result = _display(sandbox, tmp_path, output_format="json", section=section, encoding="cp1252")

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout.decode("cp1252"))["a"]["name"] == _VALUE


@os_agnostic
@pytest.mark.parametrize("section", ["", "a"], ids=["whole", "section"])
def test_the_human_view_on_a_cp1252_stdout_escapes_only_what_it_cannot_encode(
    sandbox: LayeredSandbox, tmp_path: Path, section: str
) -> None:
    result = _display(sandbox, tmp_path, output_format="human", section=section, encoding="cp1252")

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    text = result.stdout.decode("cp1252")
    assert f'"{_UMLAUT}-{_B}u6f22-{_B}U0001f600"' in text


@os_agnostic
@pytest.mark.parametrize("output_format", ["json", "human"])
def test_a_utf8_stdout_gets_every_character_as_it_is(
    sandbox: LayeredSandbox, tmp_path: Path, output_format: str
) -> None:
    result = _display(sandbox, tmp_path, output_format=output_format, section="", encoding="utf-8")

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert _VALUE in result.stdout.decode("utf-8")
