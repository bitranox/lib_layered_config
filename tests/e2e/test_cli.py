from __future__ import annotations

import json
import sys
from pathlib import Path

from click.testing import CliRunner

import lib_cli_exit_tools

from lib_layered_config import cli

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


def _write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _cli_environment(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Return the app-layer directory and env overrides for the current platform."""

    overrides: dict[str, str] = {}
    if sys.platform.startswith("win"):
        program_data = tmp_path / "ProgramData"
        appdata = tmp_path / "AppData" / "Roaming"
        local = tmp_path / "AppData" / "Local"
        overrides["LIB_LAYERED_CONFIG_PROGRAMDATA"] = str(program_data)
        overrides["LIB_LAYERED_CONFIG_APPDATA"] = str(appdata)
        overrides["LIB_LAYERED_CONFIG_LOCALAPPDATA"] = str(local)
        base = program_data / VENDOR / APP
    elif sys.platform == "darwin":
        app_support = tmp_path / "Library" / "Application Support"
        home_support = tmp_path / "HomeLibrary" / "Application Support"
        overrides["LIB_LAYERED_CONFIG_MAC_APP_ROOT"] = str(app_support)
        overrides["LIB_LAYERED_CONFIG_MAC_HOME_ROOT"] = str(home_support)
        base = app_support / VENDOR / APP
    else:
        etc_root = tmp_path / "etc"
        overrides["LIB_LAYERED_CONFIG_ETC"] = str(etc_root)
        base = etc_root / SLUG
    return base, overrides


def test_cli_read_config_outputs_json(tmp_path: Path) -> None:
    base, env = _cli_environment(tmp_path)
    _write_toml(
        base / "config.toml",
        """[service]
timeout = 15
""",
    )
    runner = CliRunner()
    result = runner.invoke(
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
        env=env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["service"]["timeout"] == 15


def test_cli_read_config_with_provenance(tmp_path: Path) -> None:
    base, env = _cli_environment(tmp_path)
    _write_toml(
        base / "config.toml",
        """[feature]
enabled = true
""",
    )
    runner = CliRunner()
    result = runner.invoke(
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
        env=env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["config"]["feature"]["enabled"] is True
    meta = payload["provenance"]["feature.enabled"]
    assert meta["layer"] == "app"
    assert meta["path"].endswith("config.toml")


def test_cli_env_prefix_command() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.cli, ["env-prefix", "config-kit"])
    assert result.exit_code == 0
    assert result.output.strip() == "CONFIG_KIT"


def test_cli_info_handles_missing_metadata(monkeypatch) -> None:
    def _raise_pkg_not_found(*_args, **_kwargs):
        raise cli.metadata.PackageNotFoundError()

    monkeypatch.setattr(cli.metadata, "metadata", _raise_pkg_not_found)
    runner = CliRunner()
    result = runner.invoke(cli.cli, ["info"])
    assert result.exit_code == 0
    assert "metadata unavailable" in result.output


def test_cli_main_restores_traceback_flag(tmp_path: Path, monkeypatch) -> None:
    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    base, env = _cli_environment(tmp_path)
    _write_toml(
        base / "config.toml",
        "value = 1\n",
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
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
    runner = CliRunner()
    result = runner.invoke(cli.cli, ["fail"])
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "i should fail"
