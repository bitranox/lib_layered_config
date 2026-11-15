"""The ``--json`` envelope: one shape on stdout for every command, on success and on failure.

Driven through ``cli.main`` so the exit code is the one a shell sees, not CliRunner's.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
import rich_click as click
from lib_cli_exit_tools import SigIntInterrupt

from lib_layered_config import cli
from lib_layered_config.cli import common as cli_common
from lib_layered_config.cli.envelope import run_in_envelope
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
IDENTITY = ["--vendor", VENDOR, "--app", APP, "--slug", SLUG]


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


def _mapping(value: object) -> dict[str, object]:
    """*value*, a JSON object, typed for the assertions that read it."""
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, object]]:
    """Run the CLI and return its exit code and the one JSON document it printed on stdout."""
    code = cli.main(list(argv), restore_traceback=True)
    return code, _mapping(json.loads(capsys.readouterr().out))


def _start(sandbox: LayeredSandbox) -> list[str]:
    # start_dir under the sandbox keeps the .env search away from the repository's own .env. The sandbox
    # creates its layer directories only when a file is written there, so make the start directory here.
    sandbox.start_dir.mkdir(parents=True, exist_ok=True)
    return ["--start-dir", str(sandbox.start_dir)]


@os_agnostic
@pytest.mark.parametrize("command", ["read", "read-json"])
def test_a_read_prints_the_config_inside_the_envelope(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    sandbox.write("app", "config.toml", content="[service]\nport = 8080\n")

    code, document = _run(capsys, command, *IDENTITY, *_start(sandbox), "--json")

    assert code == 0
    assert (document["ok"], document["command"], document["skipped"]) == (True, command, [])
    assert document["data"] == {
        "config": {"service": {"port": 8080}},
        "provenance": {
            "service.port": {"layer": "app", "path": str(sandbox.roots["app"] / "config.toml"), "key": "service.port"}
        },
    }


@os_agnostic
def test_a_read_without_provenance_keeps_the_envelope_shape_with_null_provenance(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    # A top-level table named "config" is where a bare config in data would read as the wrapper.
    sandbox.write("app", "config.toml", content="[config]\nx = 1\n")

    code, document = _run(capsys, "read", *IDENTITY, *_start(sandbox), "--no-provenance", "--json")

    assert code == 0
    assert document["data"] == {"config": {"config": {"x": 1}}, "provenance": None}


@os_agnostic
def test_a_read_without_provenance_still_masks_secrets_inside_the_envelope(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.write("app", "config.toml", content='[db]\npassword = "hunter2"\n')

    _, document = _run(capsys, "read", *IDENTITY, *_start(sandbox), "--no-provenance", "--json")

    assert document["data"] == {"config": {"db": {"password": "***REDACTED***"}}, "provenance": None}


@os_agnostic
def test_a_redacted_read_masks_the_secret_inside_the_envelope(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.write("app", "config.toml", content='[db]\npassword = "hunter2"\n')

    _, document = _run(capsys, "read-json", *IDENTITY, *_start(sandbox), "--redact", "--json")

    assert "hunter2" not in json.dumps(document)


@os_agnostic
def test_a_failed_read_prints_the_error_envelope_and_keeps_the_exit_code(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("x = [", encoding="utf-8")
    argv = ["read-json", *IDENTITY, *_start(sandbox), "--default-file", str(broken)]
    plain_code = cli.main(argv, restore_traceback=True)
    capsys.readouterr()

    code, document = _run(capsys, *argv, "--json")

    assert code == plain_code == 1
    assert (document["ok"], document["command"]) == (False, "read-json")
    error = _mapping(document["error"])
    assert (error["type"], error["exit_code"]) == ("LayerLoadError", 1)
    assert "is not valid TOML" in str(error["message"])


@os_agnostic
def test_deploy_lists_every_section_and_reports_what_it_skipped(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "source.toml"
    source.write_text("x = 1\n", encoding="utf-8")
    argv = ["deploy", "--source", str(source), *IDENTITY, "--target", "user", "--batch", "--no-permissions"]
    cli.main(argv, restore_traceback=True)
    capsys.readouterr()

    code, document = _run(capsys, *argv, "--json")

    assert code == 0
    assert (document["ok"], document["command"]) == (True, "deploy")
    data = _mapping(document["data"])
    destination = str(sandbox.roots["user"] / "config.toml")
    # The second run finds the same content already there and skips it; every section is listed, empty or not.
    assert (data["created"], data["skipped"], data["dot_d_created"]) == ([], [destination], [])
    assert document["skipped"] == [destination]


@os_agnostic
def test_a_usage_error_inside_a_command_keeps_click_exit_code(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "source.toml"
    source.write_text("x = 1\n", encoding="utf-8")
    argv = ["deploy", "--source", str(source), *IDENTITY, "--target", "user", "--no-permissions", "--dir-mode", "750"]

    code, document = _run(capsys, *argv, "--json")

    assert code == 2
    error = _mapping(document["error"])
    assert (document["ok"], error["type"], error["exit_code"]) == (False, "UsageError", 2)


def _usage_error_argv(kind: str, tmp_path: Path) -> list[str]:
    # One argv per error kind Click raises while parsing, before the command runs.
    if kind == "MissingParameter":
        return ["read", "--app", APP, "--slug", SLUG]
    if kind == "BadParameter":
        return ["deploy", "--source", str(tmp_path / "missing.toml"), *IDENTITY, "--target", "user"]
    return ["env-prefix", SLUG, "--bogus"]


@os_agnostic
@pytest.mark.parametrize("kind", ["MissingParameter", "BadParameter", "NoSuchOption"])
def test_a_usage_error_before_the_command_runs_prints_the_envelope(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, kind: str
) -> None:
    argv = _usage_error_argv(kind, tmp_path)

    code = cli.main([*argv, "--json"], restore_traceback=True)
    captured = capsys.readouterr()

    document = _mapping(json.loads(captured.out))
    error = _mapping(document["error"])
    assert (code, document["ok"], document["command"]) == (2, False, argv[0])
    assert (error["type"], error["exit_code"]) == (kind, 2)
    assert str(error["message"])
    assert "Usage:" not in captured.err


@os_agnostic
@pytest.mark.parametrize("command", ["read", "read-json", "deploy", "generate-examples", "info", "env-prefix", "fail"])
def test_every_command_prints_the_envelope_for_an_unknown_option(
    capsys: pytest.CaptureFixture[str], command: str
) -> None:
    # Click rejects an unknown option before it checks required ones, so no other argument is needed.
    code, document = _run(capsys, command, "--bogus", "--json")

    error = _mapping(document["error"])
    assert (code, document["command"], error["type"]) == (2, command, "NoSuchOption")


@os_agnostic
@pytest.mark.parametrize("kind", ["MissingParameter", "BadParameter", "NoSuchOption"])
def test_a_usage_error_without_json_keeps_click_usage_text(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, kind: str
) -> None:
    code = cli.main(_usage_error_argv(kind, tmp_path), restore_traceback=True)
    captured = capsys.readouterr()

    assert (code, captured.out) == (2, "")
    assert "Usage:" in captured.err


@os_agnostic
def test_generate_examples_lists_what_it_created(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    destination = tmp_path / "examples"

    code, document = _run(
        capsys, "generate-examples", "--destination", str(destination), *IDENTITY, "--platform", "posix", "--json"
    )

    assert code == 0
    data = _mapping(document["data"])
    created = data["created"]
    assert isinstance(created, list)
    assert str(destination / "xdg" / SLUG / "config.toml") in cast("list[str]", created)


@os_agnostic
def test_generate_examples_lists_the_files_it_kept_as_skipped(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # Without --force an existing example file is left alone; like deploy, the envelope names it in
    # ``skipped`` and in data["skipped"], rather than reporting an empty list.
    destination = str(tmp_path / "examples")
    argv = ["generate-examples", "--destination", destination, *IDENTITY, "--platform", "posix", "--json"]
    _, first = _run(capsys, *argv)
    first_created = cast("list[str]", _mapping(first["data"])["created"])

    code, second = _run(capsys, *argv)

    assert code == 0
    assert first_created
    assert second["data"] == {"created": [], "skipped": first_created}
    assert second["skipped"] == first_created


@os_agnostic
def test_info_prints_the_package_metadata(capsys: pytest.CaptureFixture[str]) -> None:
    metadata = cli_common.package_metadata

    code, document = _run(capsys, "info", "--json")

    assert code == 0
    data = _mapping(document["data"])
    assert (data["name"], data["version"], data["shell_command"]) == (
        metadata.name,
        metadata.version,
        metadata.shell_command,
    )


@os_agnostic
def test_env_prefix_prints_the_slug_and_its_prefix(capsys: pytest.CaptureFixture[str]) -> None:
    code, document = _run(capsys, "env-prefix", "config-kit", "--json")

    assert (code, document["data"]) == (0, {"slug": "config-kit", "prefix": "CONFIG_KIT___"})


@os_agnostic
def test_env_prefix_reports_an_empty_slug_as_a_usage_error_in_the_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, document = _run(capsys, "env-prefix", "", "--json")

    error = _mapping(document["error"])
    assert (code, document["ok"], error["type"], error["exit_code"]) == (2, False, "BadParameter", 2)
    assert "slug cannot be empty" in str(error["message"])


@os_agnostic
def test_fail_prints_its_error_inside_the_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    code, document = _run(capsys, "fail", "--json")

    error = _mapping(document["error"])
    assert (code, document["ok"], error["type"], error["exit_code"]) == (1, False, "RuntimeError", 1)


@os_agnostic
@pytest.mark.parametrize("interrupt", [click.Abort(), SigIntInterrupt()], ids=["click-abort", "sigint"])
def test_an_interrupt_passes_through_the_envelope_unprinted(
    capsys: pytest.CaptureFixture[str], interrupt: Exception
) -> None:
    # An interrupt is not a command result: lib_cli_exit_tools must still see it to map it to the
    # signal's exit code, so the envelope neither prints it nor turns it into a SystemExit.
    def interrupted() -> None:
        raise interrupt

    with pytest.raises(type(interrupt)):
        run_in_envelope("demo", interrupted)

    assert capsys.readouterr().out == ""
