"""A read never fails because stdout cannot encode a configuration value.

A piped stdout on Windows uses the ANSI code page (cp1252 on a German or English install), which
has no CJK characters and no emoji. Every read mode then exited 22 with nothing on stdout, the
``--json`` envelope included. JSON output now carries such a character as a ``\\uXXXX`` escape
(valid JSON, the same value once parsed), human output as a Python backslash escape, and a
character the stream can encode is written as it is. The command runs in a child process because
the stream encoding is the child's own (``PYTHONIOENCODING``).
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
    from collections.abc import Iterator
    from pathlib import Path

_KANJI = chr(0x6F22)
_EMOJI = chr(0x1F600)
_UMLAUT = chr(0xFC)
_VALUE = f"{_UMLAUT}-{_KANJI}-{_EMOJI}"
_IDENTITY = ["--vendor", "Acme", "--app", "EncodeKit", "--slug", "encode-kit"]

_JSON_MODES = [
    pytest.param(["read", "--json"], id="read-envelope"),
    pytest.param(["read", "--json", "--no-provenance"], id="read-envelope-no-provenance"),
    pytest.param(["read", "--format", "json"], id="read-format-json"),
    pytest.param(["read-json"], id="read-json"),
    pytest.param(["read-json", "--json"], id="read-json-envelope"),
]


@pytest.fixture
def sandbox(tmp_path: Path) -> LayeredSandbox:
    box = create_layered_sandbox(tmp_path, vendor="Acme", app="EncodeKit", slug="encode-kit")
    box.write("user", "config.toml", content=f'[a]\nname = "{_VALUE}"\n')
    return box


def _run(sandbox: LayeredSandbox, args: list[str], *, encoding: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, **sandbox.env, "NO_COLOR": "1", "PYTHONIOENCODING": encoding}
    env.pop("FORCE_COLOR", None)
    return subprocess.run(  # noqa: S603 - argv is this interpreter, the module and fixed arguments, no shell
        [sys.executable, "-m", "lib_layered_config", *args, *_IDENTITY, "--start-dir", str(cwd)],
        capture_output=True,
        env=env,
        cwd=str(cwd),
        timeout=120,
        check=False,
    )


def _strings(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():  # pyright: ignore[reportUnknownVariableType] - parsed JSON
            yield from _strings(value)  # pyright: ignore[reportUnknownArgumentType] - parsed JSON
    elif isinstance(node, list):
        for value in node:  # pyright: ignore[reportUnknownVariableType] - parsed JSON
            yield from _strings(value)  # pyright: ignore[reportUnknownArgumentType] - parsed JSON


@os_agnostic
@pytest.mark.parametrize("args", _JSON_MODES)
def test_json_output_on_a_cp1252_stdout_parses_back_to_the_exact_value(
    sandbox: LayeredSandbox, tmp_path: Path, args: list[str]
) -> None:
    result = _run(sandbox, args, encoding="cp1252", cwd=tmp_path)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert _VALUE in set(_strings(json.loads(result.stdout.decode("cp1252"))))


@os_agnostic
def test_json_output_escapes_only_what_the_stream_cannot_encode(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    result = _run(sandbox, ["read-json"], encoding="cp1252", cwd=tmp_path)

    text = result.stdout.decode("cp1252")
    assert f'"{_UMLAUT}-\\u6f22-\\ud83d\\ude00"' in text


@os_agnostic
def test_human_output_on_a_cp1252_stdout_escapes_the_unencodable_characters(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    result = _run(sandbox, ["read"], encoding="cp1252", cwd=tmp_path)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert f"{_UMLAUT}-\\u6f22-\\U0001f600" in result.stdout.decode("cp1252")


@os_agnostic
def test_a_utf8_stdout_gets_every_character_as_it_is(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    result = _run(sandbox, ["read-json"], encoding="utf-8", cwd=tmp_path)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert f'"{_VALUE}"' in result.stdout.decode("utf-8")
