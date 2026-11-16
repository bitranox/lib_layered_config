"""The CLI prints the library's refusals whole, without ``--traceback``.

The summary used to cut every error message at 500 characters, and a deploy refusing a configured
mode puts the CLI's "to deploy anyway" hint last: one problem with an ordinary home path already
ran past 500, so the hint was cut and the user never saw how to deploy anyway. User decision
2026-11-16 (F7): the summary keeps 4000 characters.

POSIX only: the configured modes are read only where modes apply (``modes_apply``), so on Windows
the deploy does not refuse them.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from lib_cli_exit_tools import get_system_exit_code

from lib_layered_config import cli
from tests.support import create_layered_sandbox
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


def _flat(text: str) -> str:
    """Strip colour and collapse whitespace: the console wraps a long line at its width."""
    return " ".join(_ANSI.sub("", text).split())


@posix_only
def test_a_refused_configured_mode_prints_every_problem_and_the_hint(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.write(
        "user",
        "config.d/10-perm.toml",
        content='[lib_layered_config.default_permissions]\nuser_file = "0o777"\nuser_directory = "0o777"\n',
    )
    source = tmp_path / "source.toml"
    source.write_text("a = 1\n", encoding="utf-8")
    argv = ["deploy", "--source", str(source), "--vendor", VENDOR, "--app", APP, "--slug", SLUG]

    code = cli.main([*argv, "--target", "user", "--batch"], restore_traceback=False)

    err = _flat(capsys.readouterr().err)
    assert code == get_system_exit_code(ValueError())
    assert "TRUNCATED" not in err
    assert "user_file: unsafe file mode 0o777" in err
    assert "user_directory: unsafe directory mode 0o777" in err
    assert err.endswith("which can make a user file that holds secrets readable by other accounts")
