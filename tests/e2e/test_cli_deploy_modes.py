"""deploy command: mode options and configured permissions through click."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from lib_layered_config import DeployPermissionsError, cli
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    monkeypatch.chdir(tmp_path)
    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text("[service]\nflag = true\n", encoding="utf-8")
    return path


def _args(source: Path, *extra: str) -> list[str]:
    return [
        "deploy",
        "--source",
        str(source),
        "--vendor",
        VENDOR,
        "--app",
        APP,
        "--slug",
        SLUG,
        "--target",
        "user",
        *extra,
    ]


@os_agnostic
@pytest.mark.parametrize(
    ("option", "value", "fragment"),
    [
        ("--dir-mode", "-1", "not a plain octal literal"),
        ("--dir-mode", "7_5_0", "not a plain octal literal"),
        ("--file-mode", "10000", "is outside 0..0o7777"),
        # CLI text is octal: "444" is 0o444 (r--r--r--), refused only for the missing owner write.
        ("--file-mode", "444", "no owner rw (0o600 is required)"),
        ("--file-mode", "664", "group write (0o020)"),
        ("--dir-mode", "770", "group write (0o020)"),
        ("--dir-mode", "7777", "the setuid bit (0o4000)"),
    ],
)
def test_a_refused_mode_is_a_usage_error_and_writes_nothing(
    sandbox: LayeredSandbox, source: Path, option: str, value: str, fragment: str
) -> None:
    # rich-click draws the error in a panel that wraps at the terminal width; pin a wide one and
    # compare with whitespace collapsed, so a fragment cannot be absent only because a line broke.
    env = {**sandbox.env, "COLUMNS": "400"}
    result = CliRunner().invoke(cli.cli, _args(source, option, value), env=env)
    output = " ".join(result.output.split())
    assert result.exit_code == 2
    assert f"Invalid value for '{option}'" in output
    assert fragment in output
    assert not (sandbox.roots["user"] / "config.toml").exists()


@os_agnostic
def test_a_ci_terminal_env_var_cannot_colour_the_refusal(sandbox: LayeredSandbox, source: Path) -> None:
    # rich-click forces a terminal (and colours the error panel) when GITHUB_ACTIONS is set
    # truthy and neither FORCE_COLOR nor PY_COLORS is present first; the suite-wide
    # tests/conftest.py::_plain_cli_output fixture pins FORCE_COLOR=0 so this stays plain
    # even under the real CI environment. Without that pin this assertion fails on CI.
    env = {**sandbox.env, "COLUMNS": "400", "GITHUB_ACTIONS": "true"}
    result = CliRunner().invoke(cli.cli, _args(source, "--dir-mode", "770"), env=env)
    assert result.exit_code == 2
    assert "\x1b" not in result.output


@posix_only
def test_both_modes_are_applied(sandbox: LayeredSandbox, source: Path) -> None:
    result = CliRunner().invoke(cli.cli, _args(source, "--dir-mode", "750", "--file-mode", "0o640"), env=sandbox.env)
    assert result.exit_code == 0, result.output
    deployed = sandbox.roots["user"] / "config.toml"
    assert deployed.parent.stat().st_mode & 0o7777 == 0o750
    assert deployed.stat().st_mode & 0o7777 == 0o640


@posix_only
def test_an_invalid_configured_setting_stops_the_command(sandbox: LayeredSandbox, source: Path) -> None:
    env = {**sandbox.env, "DEMO___LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__ENABLED": "maybe"}
    result = CliRunner().invoke(cli.cli, _args(source), env=env)
    assert isinstance(result.exception, DeployPermissionsError)
    message = str(result.exception)
    assert "default_permissions.enabled: must be true or false, got str 'maybe'" in message
    # The CLI user is told CLI options, both modes first; never a Python keyword.
    assert message.index("--dir-mode") < message.index("--no-permissions")
    assert "set_permissions=False" not in message
    assert not (sandbox.roots["user"] / "config.toml").exists()


@os_agnostic
@pytest.mark.parametrize("mode_option", [("--dir-mode", "750"), ("--file-mode", "640")])
def test_no_permissions_with_a_mode_is_a_usage_error(
    sandbox: LayeredSandbox, source: Path, mode_option: tuple[str, str]
) -> None:
    env = {**sandbox.env, "COLUMNS": "400"}
    result = CliRunner().invoke(cli.cli, _args(source, "--no-permissions", *mode_option), env=env)
    assert result.exit_code == 2
    assert "--no-permissions cannot be combined with --dir-mode or --file-mode" in " ".join(result.output.split())
    assert not (sandbox.roots["user"] / "config.toml").exists()


@os_agnostic
def test_no_permissions_deploys_past_a_broken_configuration(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("app", "config.toml", content="[broken\n")
    result = CliRunner().invoke(cli.cli, _args(source, "--no-permissions"), env=sandbox.env)
    assert result.exit_code == 0, result.output
    assert (sandbox.roots["user"] / "config.toml").exists()
