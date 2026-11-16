"""The CLI prints the library's warnings on stderr, one line each, in every output mode.

The library logs warnings (a ``.env`` another user owns passed over, a key whose type changes between
layers) to the ``lib_layered_config`` logger, which carries only a ``NullHandler``. A CLI user has no
logging set up, so the CLI attaches a stderr handler for the duration of a command. stdout, and with
it the ``--json`` envelope, stays unchanged.

Driven through ``cli.main`` so stdout and stderr are the ones a shell sees.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import cli
from lib_layered_config.core import read_config
from lib_layered_config.observability import bind_trace_id
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
IDENTITY = ["--vendor", VENDOR, "--app", APP, "--slug", SLUG]
# defaults say "a" is a value, the app file says it is a table: the merge logs type_conflict.
_CONFLICTING_DEFAULTS = "a = 1\n"
_CONFLICTING_APP = "[a]\nb = 2\n"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


def _start(sandbox: LayeredSandbox) -> list[str]:
    # The sandbox creates its layer directories only when a file is written there.
    sandbox.start_dir.mkdir(parents=True, exist_ok=True)
    return ["--start-dir", str(sandbox.start_dir)]


def _conflict(sandbox: LayeredSandbox, tmp_path: Path) -> list[str]:
    """Plant a type conflict between the defaults file and the app layer; return the read's arguments."""
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(_CONFLICTING_DEFAULTS, encoding="utf-8")
    sandbox.write("app", "config.toml", content=_CONFLICTING_APP)
    return [*IDENTITY, *_start(sandbox), "--default-file", str(defaults)]


def _warning_lines(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith("warning: ")]


@os_agnostic
def test_a_control_character_in_a_warning_field_is_escaped_and_the_line_stays_whole(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # User decision 2026-11-16 (R2-F3): a newline split the warning in two, and on a terminal an ESC
    # sequence went out raw. Both are written as \uXXXX; a plain key prints as before.
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('"a\\nb\\u001b[31m\\u0085" = 1\n', encoding="utf-8")
    sandbox.write("app", "config.toml", content='["a\\nb\\u001b[31m\\u0085"]\nx = 2\n')

    code = cli.main(["read", *IDENTITY, *_start(sandbox), "--default-file", str(defaults)], restore_traceback=True)

    captured = capsys.readouterr()
    assert code == 0
    (line,) = _warning_lines(captured.err)
    assert "key=a\\u000ab\\u001b[31m\\u0085 layer=app " in line
    assert len(captured.err.splitlines()) == 1


@os_agnostic
def test_a_type_conflict_reaches_stderr_naming_the_key_and_the_file(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["read", *_conflict(sandbox, tmp_path)], restore_traceback=True)

    captured = capsys.readouterr()
    assert code == 0
    (line,) = _warning_lines(captured.err)
    assert line.startswith("warning: type_conflict ")
    assert "key=a layer=app " in line
    assert f"path={sandbox.roots['app'] / 'config.toml'}" in line
    assert "trace_id" not in line
    assert "warning:" not in captured.out


@os_agnostic
def test_a_bound_trace_id_stays_out_of_the_stderr_line(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An application that binds a trace and then runs a CLI command in-process: the trace correlates
    # log entries, and means nothing to the person reading the terminal.
    bind_trace_id("trace-7f3a")
    try:
        cli.main(["read", *_conflict(sandbox, tmp_path)], restore_traceback=True)
    finally:
        bind_trace_id(None)

    (line,) = _warning_lines(capsys.readouterr().err)
    # Not a bare "trace": tmp_path is named after this test, so the path itself holds the word.
    assert "trace_id=" not in line
    assert "trace-7f3a" not in line


@os_agnostic
def test_a_warning_reaches_stderr_and_leaves_the_json_envelope_parseable(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["read", *_conflict(sandbox, tmp_path), "--json"], restore_traceback=True)

    captured = capsys.readouterr()
    assert code == 0
    assert [line.split()[1] for line in _warning_lines(captured.err)] == ["type_conflict"]
    assert json.loads(captured.out)["ok"] is True


@os_agnostic
def test_a_read_without_a_warning_prints_nothing_on_stderr(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.write("app", "config.toml", content="[a]\nb = 2\n")

    code = cli.main(["read", *IDENTITY, *_start(sandbox)], restore_traceback=True)

    assert (code, capsys.readouterr().err) == (0, "")


@os_agnostic
def test_the_handler_is_gone_after_the_command_so_a_library_read_stays_silent(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    handlers_before = list(logging.getLogger("lib_layered_config").handlers)
    cli.main(["read", *_conflict(sandbox, tmp_path)], restore_traceback=True)
    capsys.readouterr()

    read_config(
        vendor=VENDOR, app=APP, slug=SLUG, default_file=tmp_path / "defaults.toml", start_dir=str(sandbox.start_dir)
    )

    assert logging.getLogger("lib_layered_config").handlers == handlers_before
    assert capsys.readouterr().err == ""


@posix_only
def test_a_dotenv_another_user_owns_is_named_on_stderr(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The documented case (cli-reference.md Example 5). The effective uid is faked at os.geteuid: an
    # unprivileged test cannot create a file another user owns, and the uid is the OS edge the check reads.
    start = sandbox.start_dir / "project"
    start.mkdir(parents=True)
    planted = sandbox.start_dir / ".env"
    planted.write_text("DEMO___A__B=planted\n", encoding="utf-8")
    owner = planted.stat().st_uid
    if owner == 0:
        pytest.skip("the test files are root-owned, and root-owned files are trusted")
    monkeypatch.setattr(os, "geteuid", lambda: owner + 1)

    code = cli.main(["read", *IDENTITY, "--start-dir", str(start)], restore_traceback=True)

    lines = _warning_lines(capsys.readouterr().err)
    assert code == 0
    # Exactly one line: the resolver's search list and the loader's own walk both hold this file.
    (skipped,) = [line for line in lines if line.startswith("warning: dotenv_skipped_foreign_owner ")]
    assert f"path={planted}" in skipped
