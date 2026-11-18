"""What ``read --json`` and ``read-json --json`` print, byte for byte, and how they fail.

The envelope's ``data`` must be exactly the document the plain JSON output prints, parsed and written
again inside the envelope: the expected bytes are built from the plain ``read-json`` / ``read --format
json`` output, which takes its own path through the library.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from lib_cli_exit_tools import get_system_exit_code

from lib_layered_config import cli
from lib_layered_config.domain import json_codec
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
PREFIX = "DEMO___"
IDENTITY = ["--vendor", VENDOR, "--app", APP, "--slug", SLUG]

#: Every kind of value a layer can hold that JSON writes in a way of its own: a datetime, a date,
#: a time, infinity and NaN (written as null), a small float, a 64-bit integer, non-ASCII text, a
#: secret key and a URL with a password (masked by --redact), an array of tables.
_VARIED_TOML = """\
title = "Gr\\u00fc\\u00dfe \\u2713"
when = 2026-11-17T20:10:00Z
local = 2026-11-17T20:10:00
day = 2026-11-17
clock = 20:10:00
big = 18446744073709551615
small = 1e-7
hot = inf
odd = nan
negative = -0.0

[db]
password = "hunter2"
url = "postgres://alice:s3cret@db.example.invalid/app"
port = 5432

[[servers]]
name = "a"
tags = ["x", "y"]

[[servers]]
name = "b"
"""


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    # start_dir under the sandbox keeps the .env search away from the repository's own .env.
    created.start_dir.mkdir(parents=True, exist_ok=True)
    return created


def _stdout(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv), restore_traceback=True)
    return code, capsys.readouterr().out


def _expected_envelope(command: str, data: object) -> str:
    return json_codec.dumps({"ok": True, "command": command, "data": data, "skipped": []}, indent=True) + "\n"


@os_agnostic
@pytest.mark.parametrize("redact", ["--redact", "--no-redact"])
@pytest.mark.parametrize("command", ["read", "read-json"])
def test_the_envelope_with_provenance_holds_the_plain_json_output_byte_for_byte(
    sandbox: LayeredSandbox,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    redact: str,
) -> None:
    sandbox.write("app", "config.toml", content=_VARIED_TOML)
    monkeypatch.setenv(f"{PREFIX}DB__TOKEN", "abc123")
    start = ["--start-dir", str(sandbox.start_dir)]
    _, plain = _stdout(capsys, "read-json", *IDENTITY, *start, "--no-indent", redact)

    code, enveloped = _stdout(capsys, command, *IDENTITY, *start, redact, "--json")

    assert code == 0
    assert enveloped == _expected_envelope(command, json_codec.loads(plain))


@os_agnostic
@pytest.mark.parametrize("redact", ["--redact", "--no-redact"])
def test_the_envelope_without_provenance_holds_the_plain_json_output_byte_for_byte(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, redact: str
) -> None:
    sandbox.write("app", "config.toml", content=_VARIED_TOML)
    monkeypatch.setenv(f"{PREFIX}DB__TOKEN", "abc123")
    start = ["--start-dir", str(sandbox.start_dir)]
    _, plain = _stdout(capsys, "read", *IDENTITY, *start, "--format", "json", "--no-provenance", "--no-indent", redact)

    code, enveloped = _stdout(capsys, "read", *IDENTITY, *start, "--no-provenance", redact, "--json")

    assert code == 0
    assert enveloped == _expected_envelope("read", {"config": json_codec.loads(plain), "provenance": None})


@os_agnostic
def test_the_varied_fixture_masks_its_secrets_and_keeps_every_value_kind(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    """The byte comparisons above compare something: the fixture's values reach the output."""
    sandbox.write("app", "config.toml", content=_VARIED_TOML)

    _, enveloped = _stdout(capsys, "read", *IDENTITY, "--start-dir", str(sandbox.start_dir), "--json")

    config = json.loads(enveloped)["data"]["config"]
    assert (config["db"]["password"], config["db"]["url"]) == (
        "***REDACTED***",
        "postgres://alice:***REDACTED***@db.example.invalid/app",
    )
    assert (config["when"], config["hot"], config["odd"], config["big"]) == (
        "2026-11-17T20:10:00+00:00",
        None,
        None,
        18446744073709551615,
    )


def _nested(depth: int) -> str:
    return "[" * depth + "1" + "]" * depth


@os_agnostic
@pytest.mark.parametrize(
    "argv", [["read", "--json"], ["read-json", "--json"], ["read", "--no-provenance", "--json"]], ids=" ".join
)
def test_a_config_too_deep_for_the_envelope_prints_the_failure_envelope(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    """A config nested 253 levels, the most a plain JSON view writes, is two levels too deep inside the envelope.

    The envelope puts it under ``data`` and ``config``; the codec refuses level 255. The refusal keeps
    the exit code and message the command reports without ``--json``, and stdout still holds JSON.
    """
    monkeypatch.setenv(f"{PREFIX}DEEP", _nested(252))
    command, *flags = argv

    code, out = _stdout(capsys, command, *IDENTITY, "--start-dir", str(sandbox.start_dir), *flags)

    # lib_cli_exit_tools maps TypeError per OS: 22 (EINVAL) on POSIX, 87 on Windows.
    expected = get_system_exit_code(TypeError())
    assert code == expected
    assert json.loads(out) == {
        "ok": False,
        "command": command,
        "error": {"type": "TypeError", "message": "Recursion limit reached", "exit_code": expected},
    }
