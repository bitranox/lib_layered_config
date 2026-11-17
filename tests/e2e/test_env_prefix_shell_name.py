"""``env-prefix`` says when the prefix it prints is not a name a shell can export.

A slug may hold a dot (``my.app``), and the prefix keeps it (``MY.APP___``). ``os.environ`` reads such a
name, and env(1) or a container's environment can set it, but ``export MY.APP___X=1`` fails in every
POSIX shell. The prefix stays as it is, since a deployment that sets the dotted name works today; the
command now adds a note on stderr naming how to set it, and stdout and the ``--json`` data are unchanged.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import cli, read_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


@os_agnostic
@pytest.mark.parametrize("args", [["env-prefix", "my.app"], ["env-prefix", "my.app", "--json"]])
def test_a_dotted_slug_gets_a_note_on_stderr_and_an_unchanged_answer(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(args, restore_traceback=False)

    captured = capsys.readouterr()
    assert code == 0
    if "--json" in args:
        assert json.loads(captured.out)["data"] == {"slug": "my.app", "prefix": "MY.APP___"}
    else:
        assert captured.out == "MY.APP___\n"
    assert "MY.APP___" in captured.err
    assert "not a name a POSIX shell can export" in captured.err
    assert "env(1)" in captured.err


@os_agnostic
@pytest.mark.parametrize("slug", ["2app", "9"])
def test_a_slug_starting_with_a_digit_gets_a_note_with_a_remedy_that_works(
    slug: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # "2app" holds only letters and digits, so a remedy naming the allowed characters alone sends the
    # reader back to the slug they already have: the note has to name the first character too.
    code = cli.main(["env-prefix", slug], restore_traceback=False)

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == f"{slug.upper()}___\n"
    assert "does not start with a digit" in captured.err
    assert "a slug that starts with a letter" in captured.err


@os_agnostic
@pytest.mark.parametrize("slug", ["my-app", "my_app", "App2"])
def test_a_slug_giving_a_shell_name_gets_no_note(slug: str, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["env-prefix", slug], restore_traceback=False)

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""


@os_agnostic
@pytest.mark.parametrize("slug", ["my.app", "2app"])
def test_a_variable_under_an_unexportable_prefix_is_still_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slug: str
) -> None:
    create_layered_sandbox(tmp_path, vendor="Acme", app="Dotted", slug=slug).apply_env(monkeypatch)
    monkeypatch.setenv(f"{slug.upper()}___SERVICE__TIMEOUT", "15")

    config = read_config(vendor="Acme", app="Dotted", slug=slug, start_dir=str(tmp_path))

    assert config.get("service.timeout") == 15
