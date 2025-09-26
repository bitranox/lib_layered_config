"""End-to-end CLI coverage for the public commands exposed by lib-layered-config.

These tests exercise the documented CLI workflows (read, deploy, generate,
metadata lookups) using the layered sandbox to stay faithful to the precedence
order. They double as regression tests for the README examples and the module
reference CLI section.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import lib_cli_exit_tools

from lib_layered_config import cli
from tests.support import LayeredSandbox, create_layered_sandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


def _write(sandbox: LayeredSandbox, layer: str, relative: str, body: str) -> Path:
    """Helper to narrate fixture intent when shaping a specific configuration layer."""

    return sandbox.write(layer, relative, content=body)


def _runner() -> CliRunner:
    """Return a fresh CLI runner so each test starts from a clean state."""

    return CliRunner()


def test_cli_read_config_outputs_json(tmp_path: Path) -> None:
    """`cli read` should emit merged JSON respecting precedence and indentation options."""

    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    _write(
        sandbox,
        "app",
        "config.toml",
        """[service]
timeout = 15
""",
    )
    result = _runner().invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
            "--indent",
            "0",
        ],
        env=sandbox.env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["service"]["timeout"] == 15


def test_cli_read_config_with_provenance(tmp_path: Path) -> None:
    """`cli read --provenance` should emit both config and provenance payloads."""

    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    _write(
        sandbox,
        "app",
        "config.toml",
        """[feature]
enabled = true
""",
    )
    result = _runner().invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            VENDOR,
            "--app",
            APP,
            "--slug",
            SLUG,
            "--provenance",
        ],
        env=sandbox.env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["config"]["feature"]["enabled"] is True
    meta = payload["provenance"]["feature.enabled"]
    assert meta["layer"] == "app"
    assert meta["path"].endswith("config.toml")


def test_cli_deploy_command(tmp_path: Path) -> None:
    """`cli deploy` should provision selected targets and respect force semantics."""

    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    destination = sandbox.roots["user"].parent.parent
    env = dict(sandbox.env)
    if sandbox.platform.startswith("linux") or sandbox.platform == "darwin":
        env.setdefault("XDG_CONFIG_HOME", str(destination / "xdg"))

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
    runner = _runner()
    first = runner.invoke(cli.cli, command, env=env)
    assert first.exit_code == 0
    created = [Path(item) for item in json.loads(first.output)]
    assert len(created) == 2
    for path in created:
        assert path.exists()
        assert "api.example.com" in path.read_text(encoding="utf-8")

    second = runner.invoke(cli.cli, command, env=env)
    assert second.exit_code == 0
    assert json.loads(second.output) == []

    app_path = next(path for path in created if str(path).startswith(str(sandbox.roots["app"])))
    app_path.write_text("[existing]\nvalue=1\n", encoding="utf-8")

    forced = runner.invoke(cli.cli, command + ["--force"], env=env)
    assert forced.exit_code == 0
    rewritten = {Path(item) for item in json.loads(forced.output)}
    assert app_path in rewritten
    assert "api.example.com" in app_path.read_text(encoding="utf-8")


def test_cli_generate_examples_command(tmp_path: Path) -> None:
    """`cli generate-examples` should create the documented example tree and overwrite on demand."""

    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
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

    runner = _runner()
    first = runner.invoke(cli.cli, command)
    assert first.exit_code == 0
    created = [Path(item) for item in json.loads(first.output)]
    assert len(created) >= 1
    for path in created:
        assert path.exists()

    second = runner.invoke(cli.cli, command)
    assert second.exit_code == 0
    assert json.loads(second.output) == []

    target = created[0]
    target.write_text("overwrite", encoding="utf-8")

    forced = runner.invoke(cli.cli, command + ["--force"])
    assert forced.exit_code == 0
    rewritten = {Path(item) for item in json.loads(forced.output)}
    assert target in rewritten
    assert "overwrite" not in target.read_text(encoding="utf-8")


def test_cli_env_prefix_command() -> None:
    """`cli env-prefix` should echo the canonical uppercase prefix for a slug."""

    result = _runner().invoke(cli.cli, ["env-prefix", "config-kit"])
    assert result.exit_code == 0
    assert result.output.strip() == "CONFIG_KIT"


def test_cli_info_handles_missing_metadata(monkeypatch) -> None:
    """`cli info` must degrade gracefully when package metadata is unavailable."""

    def _raise_pkg_not_found(*_args, **_kwargs):
        raise cli.metadata.PackageNotFoundError()

    monkeypatch.setattr(cli.metadata, "metadata", _raise_pkg_not_found)
    result = _runner().invoke(cli.cli, ["info"])
    assert result.exit_code == 0
    assert "metadata unavailable" in result.output


def test_cli_main_restores_traceback_flag(tmp_path: Path, monkeypatch) -> None:
    """`cli main` should restore lib_cli_exit_tools tracebacks after execution."""

    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    sandbox.apply_env(monkeypatch)
    sandbox.write("app", "config.toml", content="value = 1\n")
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
    assert exit_code == 0
    assert getattr(lib_cli_exit_tools.config, "traceback", False) == previous_traceback


def test_cli_fail_command() -> None:
    """`cli fail` should bubble runtime errors for debugging flows."""

    result = _runner().invoke(cli.cli, ["fail"])
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "i should fail"
