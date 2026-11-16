"""``--traceback`` shows the full traceback however the CLI is started.

The installed console scripts call ``main()`` with no arguments, and the flag used to be found by
parsing those arguments in advance, so it did nothing there and worked only through
``python -m lib_layered_config``. User decision 2026-11-16 (R2-F1): the root command writes the flag
into ``lib_cli_exit_tools.config`` itself, as the CLI template does.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from tests.support.os_markers import os_agnostic

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TRACEBACK_MARK = "most recent call last"


def _console_script(name: str) -> list[str]:
    suffix = ".exe" if sys.platform == "win32" else ""
    script = Path(sysconfig.get_path("scripts")) / f"{name}{suffix}"
    # Every environment that runs this suite installs the package, scripts included; a missing script
    # is a broken install the test should report, not skip past.
    assert script.is_file(), f"console script not installed: {script}"
    return [str(script)]


_ENTRY_POINTS = {
    "lib_layered_config": lambda: _console_script("lib_layered_config"),
    "lib-layered-config": lambda: _console_script("lib-layered-config"),
    "python -m": lambda: [sys.executable, "-m", "lib_layered_config"],
}


def _stderr_of_fail(entry: str, *flags: str, cwd: Path) -> tuple[int, str]:
    env = {**os.environ, "HOME": str(cwd)}
    completed = subprocess.run(  # noqa: S603 - argv is this environment's own interpreter or script plus constants
        [*_ENTRY_POINTS[entry](), *flags, "fail"],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    return completed.returncode, _ANSI.sub("", completed.stderr)


@os_agnostic
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_traceback_flag_shows_the_full_traceback(entry: str, tmp_path: Path) -> None:
    code, stderr = _stderr_of_fail(entry, "--traceback", cwd=tmp_path)

    assert code == 1
    assert _TRACEBACK_MARK in stderr


@os_agnostic
@pytest.mark.parametrize("entry", list(_ENTRY_POINTS))
def test_without_the_flag_only_the_summary_is_printed(entry: str, tmp_path: Path) -> None:
    code, stderr = _stderr_of_fail(entry, cwd=tmp_path)

    assert code == 1
    assert _TRACEBACK_MARK not in stderr
    assert "RuntimeError: i should fail" in stderr
