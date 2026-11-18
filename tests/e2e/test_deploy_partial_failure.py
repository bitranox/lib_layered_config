"""A deploy that fails partway names the files it already wrote.

User decision 2026-11-16 (R2-F2, "Name what was written"): ``deploy_config`` keeps raising the same
exception and attaches the results written before it; :func:`deployed_before_failure` reads them
back. The CLI prints those paths on stderr before the error, and the ``--json`` failure envelope gains
a ``written`` list, present only when something was written. Targets are written in the order given,
so the same failure leaves a different set of files depending on that order.
"""

from __future__ import annotations

import io
import json
import os
import sys
from typing import TYPE_CHECKING, cast

import click
import click.termui
import pytest
from lib_cli_exit_tools import SigIntInterrupt

from lib_layered_config import cli
from lib_layered_config.deploy import DeployAction, DeployResult, deploy_config, deployed_before_failure
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
IDENTITY = ["--vendor", VENDOR, "--app", APP, "--slug", SLUG]


class _RefusedError(Exception):
    """What the test's conflict resolver raises: a prompt the user declined."""


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


def _source(tmp_path: Path, *, dot_d: bool = False) -> Path:
    source = tmp_path / "source" / "config.toml"
    source.parent.mkdir(parents=True)
    source.write_text("new = 1\n", encoding="utf-8")
    if dot_d:
        (source.parent / "config.d").mkdir()
        (source.parent / "config.d" / "10-a.toml").write_text("part = 1\n", encoding="utf-8")
    return source


def _config(sandbox: LayeredSandbox, layer: str) -> Path:
    return sandbox.roots[layer] / "config.toml"


def _existing(path: Path) -> Path:
    """Put a file at *path* whose content differs from the source, so deploying there is a conflict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old = 1\n", encoding="utf-8")
    return path


def _refuse(path: Path) -> DeployAction:
    raise _RefusedError(str(path))


def _deploy(source: Path, *targets: str) -> list[DeployResult]:
    with pytest.raises(_RefusedError) as caught:
        deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=list(targets), conflict_resolver=_refuse)
    return list(deployed_before_failure(caught.value))


@os_agnostic
def test_a_failure_on_the_second_target_names_the_first_one_written(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    _existing(_config(sandbox, "app"))

    with pytest.raises(_RefusedError) as caught:
        deploy_config(
            _source(tmp_path), vendor=VENDOR, app=APP, slug=SLUG, targets=["user", "app"], conflict_resolver=_refuse
        )

    written = deployed_before_failure(caught.value)
    assert [(result.destination.resolve(), result.action) for result in written] == [
        (_config(sandbox, "user").resolve(), DeployAction.CREATED)
    ]


@os_agnostic
def test_the_same_failure_on_the_first_target_names_nothing(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    _existing(_config(sandbox, "app"))

    assert _deploy(_source(tmp_path), "app", "user") == []
    assert not _config(sandbox, "user").exists()


@os_agnostic
def test_a_failure_in_the_dot_d_copy_names_the_config_written_before_it(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    _existing(sandbox.roots["user"] / "config.d" / "10-a.toml")

    with pytest.raises(_RefusedError) as caught:
        deploy_config(
            _source(tmp_path, dot_d=True),
            vendor=VENDOR,
            app=APP,
            slug=SLUG,
            targets=["user"],
            conflict_resolver=_refuse,
        )

    written = deployed_before_failure(caught.value)
    assert [(result.destination.resolve(), result.action, result.dot_d_results) for result in written] == [
        (_config(sandbox, "user").resolve(), DeployAction.CREATED, ())
    ]


@os_agnostic
def test_an_error_no_deploy_raised_names_nothing() -> None:
    assert deployed_before_failure(ValueError("not from a deploy")) == []


def _cli(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, str, str]:
    """Run the CLI with nothing to read on stdin, so a conflict's prompt is a usage error."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    code = cli.main(list(argv), restore_traceback=True)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _deploy_argv(source: Path, *targets: str) -> list[str]:
    return ["deploy", "--source", str(source), *IDENTITY, *(arg for target in targets for arg in ("--target", target))]


@os_agnostic
def test_the_cli_names_the_written_file_on_stderr_before_the_error(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing(_config(sandbox, "app"))

    code, _, err = _cli(capsys, monkeypatch, *_deploy_argv(_source(tmp_path), "user", "app"))

    assert code == 2
    assert f"deploy stopped after writing:\n  {_config(sandbox, 'user')}\n" in err


@os_agnostic
def test_the_json_failure_envelope_lists_what_was_written(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing(_config(sandbox, "app"))

    code, out, _ = _cli(capsys, monkeypatch, *_deploy_argv(_source(tmp_path), "user", "app"), "--json")

    error = cast("dict[str, object]", json.loads(out)["error"])
    assert (code, error["exit_code"], error["written"]) == (2, 2, [str(_config(sandbox, "user"))])


@os_agnostic
def test_a_file_left_alone_because_it_was_identical_is_not_named_as_written(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    user = _config(sandbox, "user")
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_bytes(source.read_bytes())
    _existing(_config(sandbox, "app"))

    code, out, _ = _cli(capsys, monkeypatch, *_deploy_argv(source, "user", "app"), "--json")

    assert code == 2
    assert "written" not in json.loads(out)["error"]


@posix_only
def test_a_forced_overwrite_names_its_backup_and_the_file(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform == "win32" or os.geteuid() == 0:  # narrows os.geteuid for pyright
        pytest.skip("root writes through a read-only directory")
    user = _existing(_config(sandbox, "user"))
    walled = _config(sandbox, "app").parent
    walled.mkdir(parents=True, exist_ok=True)
    walled.chmod(0o555)  # --no-permissions below: a permission-setting deploy would chmod it back
    try:
        argv = [*_deploy_argv(_source(tmp_path), "user", "app"), "--force", "--no-permissions", "--json"]
        code, out, _ = _cli(capsys, monkeypatch, *argv)
    finally:
        walled.chmod(0o755)

    error = cast("dict[str, object]", json.loads(out)["error"])
    written = cast("list[str]", error["written"])
    assert (code, error["type"], len(written), written[-1]) == (13, "PermissionError", 2, str(user))
    assert written[0].startswith(str(user)) and written[0].endswith(".bak")


@os_agnostic
def test_the_json_failure_envelope_has_no_written_list_when_nothing_was_written(
    sandbox: LayeredSandbox, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing(_config(sandbox, "app"))

    code, out, err = _cli(capsys, monkeypatch, *_deploy_argv(_source(tmp_path), "app", "user"), "--json")

    assert code == 2
    assert sorted(cast("dict[str, object]", json.loads(out)["error"])) == ["exit_code", "message", "type"]
    assert "deploy stopped after writing" not in err


@posix_only
def test_a_control_character_in_a_written_path_is_escaped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # User decision 2026-11-16 (R2-F3): the list is one path per line, so a newline in a path must not
    # start a new one.
    created = create_layered_sandbox(tmp_path / "x\ny", vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    _existing(_config(created, "app"))

    code, _, err = _cli(capsys, monkeypatch, *_deploy_argv(_source(tmp_path), "user", "app"))

    escaped = str(_config(created, "user")).replace("\n", "\\u000a")
    assert code == 2
    assert f"deploy stopped after writing:\n  {escaped}\n" in err


def _interrupting(error: BaseException) -> Callable[..., str]:
    def read(*_args: object, **_kwargs: object) -> str:
        raise error

    return read


# click reads the prompt's answer through its module-level ``visible_prompt_func``: the one seam
# that reaches an interrupt at the conflict prompt without a terminal. A KeyboardInterrupt there
# becomes click.Abort (exit 1); lib_cli_exit_tools' SIGINT handler raises SigIntInterrupt (130).
@os_agnostic
@pytest.mark.parametrize("mode", [[], ["--json"]], ids=["human", "json"])
@pytest.mark.parametrize(
    ("interrupt", "expected_code"),
    [(KeyboardInterrupt(), 1), (SigIntInterrupt(), 130)],
    ids=["ctrl-c-at-prompt", "sigint"],
)
def test_a_deploy_interrupted_at_the_prompt_names_what_it_wrote(
    sandbox: LayeredSandbox,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: list[str],
    interrupt: BaseException,
    expected_code: int,
) -> None:
    _existing(_config(sandbox, "app"))
    monkeypatch.setattr(click.termui, "visible_prompt_func", _interrupting(interrupt))

    code, out, err = _cli(capsys, monkeypatch, *_deploy_argv(_source(tmp_path), "user", "app"), *mode)

    # stdout stays empty in both modes: an interrupt is not a command result.
    assert (code, out) == (expected_code, "")
    assert f"deploy stopped after writing:\n  {_config(sandbox, 'user')}\n" in err
