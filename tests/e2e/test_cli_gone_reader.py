"""A run whose stdout reader went away exits with the broken-pipe code (141) and prints nothing.

User decision 2026-11-16 (R2-F6): ``lib_layered_config info | head -0`` and friends used to exit 1 (click's
own ``main()`` turns ``EPIPE`` into ``SystemExit(1)``) or 120 with an "Exception ignored ...
BrokenPipeError" line when the output was smaller than the stream buffer (measured on Linux; on
Windows, where a closed pipe reports a bare ``EINVAL``, lib_cli_exit_tools' own tests measured 120 or
22 with ``OSError: [Errno 22]`` lines through the same ``run_cli`` path). The fix lives in
``lib_cli_exit_tools.run_cli`` (2.5.0), which this CLI runs every command through; these tests pin
that this CLI gets it.

Each child starts with its stdout reader already closed, so its first write meets a gone reader.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_BROKEN_PIPE_EXIT = 141


def _run(argv: list[str], *, cwd: Path, reader_gone: bool) -> tuple[int, str]:
    env = {**os.environ, "HOME": str(cwd), "USERPROFILE": str(cwd)}
    read_end, write_end = os.pipe()
    if reader_gone:
        os.close(read_end)
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is this environment's own interpreter plus constants
            [sys.executable, "-m", "lib_layered_config", *argv],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=write_end,
            stderr=subprocess.PIPE,
        )
    finally:
        os.close(write_end)
    try:
        _, stderr = process.communicate(timeout=120)
    finally:
        if not reader_gone:
            os.close(read_end)
    return process.returncode, stderr.decode("utf-8", "replace")


@os_agnostic
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["info"], id="info"),
        pytest.param(["env-prefix", "demo"], id="env-prefix"),
        pytest.param(["--version"], id="click's own version printer"),
        pytest.param(["--help"], id="help"),
    ],
)
def test_a_gone_reader_exits_with_the_broken_pipe_code_and_says_nothing(argv: list[str], tmp_path: Path) -> None:
    assert _run(argv, cwd=tmp_path, reader_gone=True) == (_BROKEN_PIPE_EXIT, "")


@os_agnostic
def test_a_failing_command_keeps_its_own_exit_code_when_the_reader_is_gone(tmp_path: Path) -> None:
    expected_code, _ = _run(["fail"], cwd=tmp_path, reader_gone=False)

    code, _ = _run(["fail"], cwd=tmp_path, reader_gone=True)

    assert expected_code not in (0, _BROKEN_PIPE_EXIT)
    assert code == expected_code
