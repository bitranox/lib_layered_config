"""The deploy conflict prompt talks on stderr, and an unanswerable prompt is a usage error.

stdout carries the JSON result that scripts parse, so a prompt written there breaks the parse as
soon as one destination conflicts. When no answer can be read (stdin at end of file), the command
must say how to run unattended (--batch or --force) instead of a bare ``Abort``. The command runs
in a child process: the stream split and the exit code are what the console entry point produces.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
import click.termui
import pytest

from lib_layered_config.cli.deploy import (
    _prompt_for_action,  # pyright: ignore[reportPrivateUsage] - Ctrl-C at the prompt needs a terminal, so the subprocess route cannot reach it
)
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable

_IDENTITY = ["--vendor", "Acme", "--app", "PromptKit", "--slug", "prompt-kit", "--target", "user"]


@pytest.fixture
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor="Acme", app="PromptKit", slug="prompt-kit")


def _deploy(sandbox: LayeredSandbox, source: Path, *, answer: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **sandbox.env, "NO_COLOR": "1"}
    env.pop("FORCE_COLOR", None)
    return subprocess.run(  # noqa: S603 - argv is this interpreter, the module and test paths, no shell
        [sys.executable, "-m", "lib_layered_config", "deploy", "--source", str(source), *_IDENTITY],
        input=answer,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd),
        timeout=120,
        check=False,
    )


def _conflicting_source(sandbox: LayeredSandbox, tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source.toml"
    source.write_text("[service]\nport = 1\n", encoding="utf-8")
    first = _deploy(sandbox, source, answer="", cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    destination = json.loads(first.stdout)["created"][0]
    source.write_text("[service]\nport = 2\n", encoding="utf-8")
    return source, Path(destination)


@os_agnostic
def test_an_answered_prompt_leaves_stdout_to_the_json_result(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source, destination = _conflicting_source(sandbox, tmp_path)

    result = _deploy(sandbox, source, answer="o\n", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["overwritten"] == [str(destination)]
    assert "File exists" in result.stderr


@os_agnostic
def test_a_prompt_with_no_answer_is_a_usage_error_naming_the_unattended_flags(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    source, destination = _conflicting_source(sandbox, tmp_path)

    result = _deploy(sandbox, source, answer="", cwd=tmp_path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--batch" in result.stderr
    assert "--force" in result.stderr
    assert destination.name in result.stderr
    assert "port = 1" in destination.read_text(encoding="utf-8")


def _raising(error: type[BaseException]) -> Callable[[str], str]:
    def read(_prompt: str) -> str:
        raise error

    return read


# click reads the answer through its module-level ``visible_prompt_func``: the one seam into a
# third-party prompt, used to tell end of input from Ctrl-C without a terminal.
@os_agnostic
@pytest.mark.parametrize(
    ("error", "expected"),
    [(EOFError, click.UsageError), (KeyboardInterrupt, click.Abort)],
    ids=["end-of-input", "ctrl-c"],
)
def test_only_end_of_input_becomes_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, error: type[BaseException], expected: type[Exception]
) -> None:
    monkeypatch.setattr(click.termui, "visible_prompt_func", _raising(error))

    with pytest.raises(expected) as caught:
        _prompt_for_action(Path("config.toml"))

    assert type(caught.value) is expected
