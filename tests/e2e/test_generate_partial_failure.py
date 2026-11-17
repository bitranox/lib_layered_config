"""A generate-examples run that fails part-way names the example files it already wrote.

As for deploy (user decision 2026-11-16, R2-F2, "Name what was written"): ``generate_examples`` and
``generate_examples_report`` keep raising the same exception and attach the paths written before it;
:func:`generated_before_failure` reads them back. The CLI prints those paths on stderr before the
error, and the ``--json`` failure envelope gains a ``written`` list, present only when something was
written. The failure here is the ``mkdir`` of a later example's directory failing (a permission
wall, raised from an audit hook on the real call): the examples are written in a fixed order, so the
files before it are written and the rest are not, on every OS. A regular file where that directory
belongs is no such failure: it is refused before anything is written.
"""

from __future__ import annotations

import contextlib
import errno
import io
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from lib_cli_exit_tools import SigIntInterrupt

from lib_layered_config import GenerateDestinationError, cli
from lib_layered_config.generate import generate_examples, generate_examples_report, generated_before_failure
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from lib_layered_config.generate import ExamplesReport

ARGV_IDENTITY = ["--slug", "demo", "--vendor", "Acme", "--app", "Demo", "--platform", "posix"]


def _first_two(destination: Path) -> list[Path]:
    """The two app-layer examples the POSIX layout writes before any under ``home/``."""
    return [destination / "xdg" / "demo" / "config.toml", destination / "xdg" / "demo" / "hosts" / "your-hostname.toml"]


def _report(destination: Path) -> ExamplesReport:
    return generate_examples_report(destination, slug="demo", vendor="Acme", app="Demo", platform="posix")


def _plain(destination: Path) -> list[Path]:
    return generate_examples(destination, slug="demo", vendor="Acme", app="Demo", platform="posix")


@os_agnostic
@pytest.mark.parametrize("generate", [_report, _plain], ids=["report", "plain"])
def test_a_failure_part_way_names_the_examples_already_written(
    tmp_path: Path, generate: Callable[[Path], object]
) -> None:
    destination = tmp_path / "out"

    with _mkdir_fails(destination / "home"), pytest.raises(PermissionError) as caught:
        generate(destination)

    written = generated_before_failure(caught.value)
    assert written == _first_two(destination)
    assert all(path.is_file() for path in written)


@os_agnostic
def test_a_failure_before_the_first_write_names_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "out"

    with _mkdir_fails(destination / "xdg"), pytest.raises(PermissionError) as caught:
        _report(destination)

    assert generated_before_failure(caught.value) == []


def test_an_error_no_generate_raised_names_nothing() -> None:
    assert generated_before_failure(ValueError("not from generate-examples")) == []


def _cli(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    code = cli.main(list(argv), restore_traceback=True)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@os_agnostic
def test_the_cli_names_the_written_examples_on_stderr_before_the_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "out"

    with _mkdir_fails(destination / "home"):
        code, _, err = _cli(capsys, monkeypatch, "generate-examples", "--destination", str(destination), *ARGV_IDENTITY)

    listing = "".join(f"  {path}\n" for path in _first_two(destination))
    assert code != 0
    assert f"generate-examples stopped after writing:\n{listing}" in err


@os_agnostic
def test_the_json_failure_envelope_lists_the_written_examples(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "out"

    with _mkdir_fails(destination / "home"):
        code, out, _ = _cli(
            capsys, monkeypatch, "generate-examples", "--destination", str(destination), *ARGV_IDENTITY, "--json"
        )

    error = cast("dict[str, object]", json.loads(out)["error"])
    assert code != 0
    assert (error["exit_code"], error["written"]) == (code, [str(path) for path in _first_two(destination)])


@os_agnostic
def test_the_json_failure_envelope_has_no_written_list_when_nothing_was_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "out"

    with _mkdir_fails(destination / "xdg"):
        code, out, err = _cli(
            capsys, monkeypatch, "generate-examples", "--destination", str(destination), *ARGV_IDENTITY, "--json"
        )

    assert code != 0
    assert sorted(cast("dict[str, object]", json.loads(out)["error"])) == ["exit_code", "message", "type"]
    assert "stopped after writing" not in err


class _MkdirFault:
    """The directory whose creation fails, and what it raises; ``at`` is ``None`` when disarmed."""

    def __init__(self) -> None:
        self.at: Path | None = None
        self.error: BaseException = SigIntInterrupt()


_FAULT = _MkdirFault()


def _fail_on_mkdir(event: str, args: tuple[object, ...]) -> None:
    # An audit hook cannot be removed, so it acts only while armed, and disarms itself on firing.
    # Raised from the hook, the error surfaces from the real os.mkdir call inside the write loop, as
    # a permission wall, or lib_cli_exit_tools' SIGINT handler, would raise it there.
    if event != "os.mkdir" or not args or _FAULT.at is None:
        return
    target = args[0]
    if isinstance(target, (str, Path)) and Path(target) == _FAULT.at:
        _FAULT.at = None
        raise _FAULT.error


sys.addaudithook(_fail_on_mkdir)


@contextlib.contextmanager
def _mkdir_fails(at: Path, error: BaseException | None = None) -> Generator[None, None, None]:
    """Make the ``mkdir`` of *at* raise *error* (a permission wall by default) while the block runs."""
    _FAULT.at = at
    _FAULT.error = error if error is not None else PermissionError(errno.EACCES, "Permission denied", str(at))
    try:
        yield
    finally:
        _FAULT.at = None


@os_agnostic
def test_an_interrupted_json_run_names_the_written_examples_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The envelope passes an interrupt through unprinted, so stderr is the only place left to say it.
    destination = tmp_path / "out"
    destination.mkdir()
    with _mkdir_fails(destination / "home", SigIntInterrupt()):
        code, out, err = _cli(
            capsys, monkeypatch, "generate-examples", "--destination", str(destination), *ARGV_IDENTITY, "--json"
        )

    listing = "".join(f"  {path}\n" for path in _first_two(destination))
    assert (code, out) == (130, "")
    assert f"generate-examples stopped after writing:\n{listing}" in err


@os_agnostic
def test_a_file_where_an_example_directory_belongs_is_refused_before_anything_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    blocker = destination / "home"
    blocker.write_text("not a directory\n", encoding="utf-8")

    code, out, err = _cli(
        capsys, monkeypatch, "generate-examples", "--destination", str(destination), *ARGV_IDENTITY, "--json"
    )

    error = cast("dict[str, object]", json.loads(out)["error"])
    assert (error["type"], error["exit_code"]) == (GenerateDestinationError.__name__, code)
    assert "written" not in error
    assert "stopped after writing" not in err
    assert sorted(path.name for path in destination.iterdir()) == ["home"]
