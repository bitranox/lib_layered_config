"""End-to-end CLI stories told as tiny, declarative poems."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import lib_cli_exit_tools

from lib_layered_config import cli
from lib_layered_config.cli import common as cli_common
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


def make_runner() -> CliRunner:
    return CliRunner()


def layer(sandbox: LayeredSandbox, target: str, relative: str, body: str) -> Path:
    return sandbox.write(target, relative, content=body)


@os_agnostic
def test_cli_read_json_without_provenance_returns_config_data(sandbox: LayeredSandbox) -> None:
    layer(
        sandbox,
        "app",
        "config.toml",
        """[service]\ntimeout = 15\n""",
    )
    result = make_runner().invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
            "--format",
            "json",
            "--no-indent",
            "--no-provenance",
        ],
        env=sandbox.env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["service"]["timeout"] == 15


@os_agnostic
def test_cli_read_json_with_provenance_includes_layer_metadata(sandbox: LayeredSandbox) -> None:
    layer(
        sandbox,
        "app",
        "config.toml",
        """[feature]\nenabled = true\n""",
    )
    result = make_runner().invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
            "--format",
            "json",
        ],
        env=sandbox.env,
    )
    payload = json.loads(result.output)
    provenance = payload["provenance"]["feature.enabled"]
    assert provenance["layer"] == "app"


@os_agnostic
def test_cli_read_human_output_lists_values_and_provenance(sandbox: LayeredSandbox) -> None:
    layer(
        sandbox,
        "app",
        "config.toml",
        """[feature]\nflag = true\n""",
    )
    result = make_runner().invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
        ],
        env=sandbox.env,
    )
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert any(line.startswith("feature.flag:") for line in lines)


@os_agnostic
def test_cli_read_respects_default_file_precedence(tmp_path: Path, sandbox: LayeredSandbox) -> None:
    default_file = tmp_path / "defaults.toml"
    default_file.write_text(
        """[service]\nmode = \"defaults\"\n""",
        encoding="utf-8",
    )
    layer(
        sandbox,
        "app",
        "config.toml",
        """[service]\nmode = \"app\"\n""",
    )
    result = make_runner().invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
            "--default-file",
            str(default_file),
            "--format",
            "json",
            "--no-provenance",
        ],
        env=sandbox.env,
    )
    payload = json.loads(result.output)
    assert payload["service"]["mode"] == "app"


@os_agnostic
def test_cli_deploy_first_run_creates_requested_targets(tmp_path: Path, sandbox: LayeredSandbox) -> None:
    source = tmp_path / "source.toml"
    source.write_text('[service]\nendpoint = "https://api.example.com"\n', encoding="utf-8")
    command = [
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
        "app",
        "--target",
        "user",
    ]
    result = make_runner().invoke(cli.cli, command, env=sandbox.env)
    output = json.loads(result.output)
    created = {Path(item) for item in output.get("created", [])}
    assert result.exit_code == 0 and len(created) == 2 and all(path.exists() for path in created)


@os_agnostic
def test_cli_deploy_rerun_without_force_skips_existing(tmp_path: Path, sandbox: LayeredSandbox) -> None:
    source = tmp_path / "source.toml"
    source.write_text("[service]\nv = 1\n", encoding="utf-8")
    command = [
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
        "app",
        "--batch",  # Non-interactive mode (identical content smart-skipped)
    ]
    runner = make_runner()
    runner.invoke(cli.cli, command, env=sandbox.env)
    repeat = runner.invoke(cli.cli, command, env=sandbox.env)
    output = json.loads(repeat.output)
    assert repeat.exit_code == 0 and output.get("skipped", []) != []


@os_agnostic
def test_cli_deploy_force_overwrites_existing_file(tmp_path: Path, sandbox: LayeredSandbox) -> None:
    source = tmp_path / "source.toml"
    source.write_text('[service]\nvalue = "new"\n', encoding="utf-8")
    destination = sandbox.roots["app"] / "config.toml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('[service]\nvalue = "old"\n', encoding="utf-8")
    command = [
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
        "app",
        "--force",
    ]
    result = make_runner().invoke(cli.cli, command, env=sandbox.env)
    assert result.exit_code == 0 and "new" in destination.read_text(encoding="utf-8")


@os_agnostic
def test_cli_generate_examples_creates_example_tree(tmp_path: Path) -> None:
    destination = tmp_path / "examples"
    command = [
        "generate-examples",
        "--destination",
        str(destination),
        "--slug",
        SLUG,
        "--vendor",
        VENDOR,
        "--app",
        APP,
        "--platform",
        "posix",
    ]
    result = make_runner().invoke(cli.cli, command)
    created = [Path(item) for item in json.loads(result.output)]
    assert result.exit_code == 0 and all(path.exists() for path in created)


@os_agnostic
def test_cli_generate_examples_second_run_skips_when_unchanged(tmp_path: Path) -> None:
    destination = tmp_path / "examples"
    command = [
        "generate-examples",
        "--destination",
        str(destination),
        "--slug",
        SLUG,
        "--vendor",
        VENDOR,
        "--app",
        APP,
    ]
    runner = make_runner()
    runner.invoke(cli.cli, command)
    second = runner.invoke(cli.cli, command)
    assert second.exit_code == 0 and json.loads(second.output) == []


@os_agnostic
def test_cli_generate_examples_force_overwrites_payload(tmp_path: Path) -> None:
    destination = tmp_path / "examples"
    command = [
        "generate-examples",
        "--destination",
        str(destination),
        "--slug",
        SLUG,
        "--vendor",
        VENDOR,
        "--app",
        APP,
    ]
    runner = make_runner()
    initial = runner.invoke(cli.cli, command)
    assert initial.exit_code == 0
    created = [Path(item) for item in json.loads(initial.output)]
    target = created[0]
    target.write_text("overwrite", encoding="utf-8")
    forced = runner.invoke(cli.cli, command + ["--force"])
    assert forced.exit_code == 0 and "overwrite" not in target.read_text(encoding="utf-8")


@os_agnostic
def test_cli_env_prefix_echoes_uppercase_slug() -> None:
    result = make_runner().invoke(cli.cli, ["env-prefix", "config-kit"])
    assert result.exit_code == 0 and result.output.strip() == "CONFIG_KIT___"


@os_agnostic
def test_cli_info_recites_real_metadata() -> None:
    metadata = importlib.reload(cli_common.package_metadata)
    expected_lines = _expected_info_lines(metadata)

    result = make_runner().invoke(cli.cli, ["info"])

    assert result.exit_code == 0
    assert result.output.splitlines() == list(expected_lines)


@os_agnostic
def test_cli_main_restores_traceback_flag_after_run(sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    previous = getattr(lib_cli_exit_tools.config, "traceback", False)
    sandbox.apply_env(monkeypatch)
    layer(sandbox, "app", "config.toml", "value = 1\n")
    exit_code = cli.main(
        [
            "--traceback",
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
        ],
        restore_traceback=True,
    )
    assert exit_code == 0 and getattr(lib_cli_exit_tools.config, "traceback", False) == previous


@os_agnostic
def test_cli_fail_command_surfaces_runtime_error() -> None:
    result = make_runner().invoke(cli.cli, ["fail"])
    assert result.exit_code != 0 and isinstance(result.exception, RuntimeError)


def _expected_info_lines(metadata: object) -> tuple[str, ...]:
    fields = (
        ("name", metadata.name),
        ("title", metadata.title),
        ("version", metadata.version),
        ("homepage", metadata.homepage),
        ("author", metadata.author),
        ("author_email", metadata.author_email),
        ("shell_command", metadata.shell_command),
    )
    pad = max(len(label) for label, _ in fields)
    lines = [f"Info for {metadata.name}:", ""]
    lines.extend(f"    {label.ljust(pad)} = {value}" for label, value in fields)
    return tuple(lines)
