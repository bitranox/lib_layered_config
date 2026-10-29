"""An explicit .env path may name a stream, not only a regular file.

A shell process substitution (``--env-file <(printf 'KEY=value')``) hands the program a FIFO such as
``/dev/fd/63``. Such a path used to load nothing, silently, as if it did not exist. It is now read,
with the same size cap a regular file has, so an endless source (a device such as ``/dev/zero``) is
refused at the cap instead of being read forever. A path that does not exist still loads nothing.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.core import LayerLoadError
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

VENDOR = "Acme"
APP = "Probe"
SLUG = "fifo-probe"
_PAYLOAD = b"SSH__KEY=/opt/keys/id\n"


@pytest.fixture()
def fifo(tmp_path: Path) -> Iterator[Path]:
    """A FIFO with a writer thread that delivers ``_PAYLOAD`` once a reader opens it."""
    path = tmp_path / "env.fifo"
    os.mkfifo(path)
    writer = threading.Thread(target=path.write_bytes, args=(_PAYLOAD,), daemon=True)
    writer.start()
    yield path
    _finish_writer(path, writer)


def _finish_writer(path: Path, writer: threading.Thread, *, grace: float = 5.0) -> None:
    """Wait for the FIFO's writer thread, failing the test when nothing ever opened the FIFO.

    A writer that delivered can still be alive for a moment after its close, so a bare
    ``is_alive()`` check cannot tell it from one stuck in ``open()``: join first. Only a writer
    still alive after that is waiting for a reader. It is released with a NON-blocking open, which
    returns at once either way; a blocking open would wait for good if the writer had just left.
    """
    writer.join(timeout=grace)
    if not writer.is_alive():
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        writer.join(timeout=5)
    finally:
        os.close(descriptor)
    pytest.fail("the code under test never opened the FIFO")


@posix_only
def test_the_loader_reads_a_fifo_named_as_the_dotenv_path(fifo: Path) -> None:
    loader = DefaultDotEnvLoader()

    data = loader.load(dotenv_path=str(fifo))

    assert data == {"ssh": {"key": "/opt/keys/id"}}
    assert loader.last_loaded_path == str(fifo)


@posix_only
def test_read_config_reads_a_fifo_and_names_it_as_the_origin(
    tmp_path: Path, fifo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path=str(fifo))

    assert config.get("ssh.key") == "/opt/keys/id"
    origin = config.origin("ssh.key")
    assert origin is not None
    assert origin["path"] == str(fifo)


def _run_bounded(call: Callable[[], None], seconds: float) -> tuple[bool, BaseException | None]:
    """Run *call* on a daemon thread; return whether it returned in time, and what it raised."""
    raised: list[BaseException] = []

    def target() -> None:
        try:
            call()
        except BaseException as error:
            raised.append(error)

    runner = threading.Thread(target=target, daemon=True)
    runner.start()
    runner.join(timeout=seconds)
    return not runner.is_alive(), (raised[0] if raised else None)


@posix_only
def test_the_fifo_teardown_waits_for_a_writer_that_already_delivered(tmp_path: Path) -> None:
    """The writer thread outlives its write by a moment: the FIFO was read, the thread has not
    exited yet. The teardown used to take that for "nobody opened it" and open the FIFO itself,
    which blocks for good with no writer left; it hung a CI job until the job timeout."""
    path = tmp_path / "env.fifo"
    os.mkfifo(path)

    def write_then_linger() -> None:
        path.write_bytes(_PAYLOAD)
        time.sleep(0.5)

    writer = threading.Thread(target=write_then_linger, daemon=True)
    writer.start()
    assert path.read_bytes() == _PAYLOAD

    finished, raised = _run_bounded(lambda: _finish_writer(path, writer), seconds=3)

    assert finished, "the teardown blocked opening a FIFO whose writer had already left"
    assert raised is None


@posix_only
def test_the_fifo_teardown_fails_when_nothing_opened_the_fifo(tmp_path: Path) -> None:
    """A writer still waiting in open() means the code under test never read the FIFO: the
    teardown releases it and fails the test rather than hang or pass."""
    path = tmp_path / "env.fifo"
    os.mkfifo(path)
    writer = threading.Thread(target=path.write_bytes, args=(_PAYLOAD,), daemon=True)
    writer.start()

    finished, raised = _run_bounded(lambda: _finish_writer(path, writer, grace=0.2), seconds=15)

    assert finished
    assert isinstance(raised, pytest.fail.Exception)
    assert "never opened the FIFO" in str(raised)
    assert not writer.is_alive()


#: Long enough for a cold interpreter start on a slow CI runner; a FIFO read never takes this long.
_CLI_TIMEOUT_SECONDS = 120


@posix_only
def test_the_read_command_takes_a_fifo_as_env_file(tmp_path: Path, fifo: Path) -> None:
    # A real process, as a shell runs `--env-file <(...)`. If the read ever blocks, the timeout ends
    # the test with every thread's stack (faulthandler prints them on SIGABRT) instead of stalling
    # the whole CI job.
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    args = ["read", "--vendor", VENDOR, "--app", APP, "--slug", SLUG, "--format", "json", "--no-provenance"]
    command = [sys.executable, "-X", "faulthandler", "-m", "lib_layered_config", *args, "--env-file", str(fifo)]

    with subprocess.Popen(  # noqa: S603 - argv is this interpreter and constants, no shell
        command, env={**os.environ, **sandbox.env}, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process:
        try:
            out, err = process.communicate(timeout=_CLI_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGABRT)
            _, err = process.communicate()
            pytest.fail("read --env-file <fifo> hung:\n" + err.decode("utf-8", errors="replace"))

    assert process.returncode == 0, err.decode("utf-8", errors="replace")
    assert json.loads(out) == {"ssh": {"key": "/opt/keys/id"}}


@posix_only
def test_an_endless_device_is_refused_at_the_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    with pytest.raises(LayerLoadError, match="exceeding the 10485760-byte limit"):
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path="/dev/zero")


@os_agnostic
def test_a_missing_dotenv_path_still_loads_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(
        vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path=str(tmp_path / "absent.env")
    )

    assert config.as_dict() == {}
