from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import lib_cli_exit_tools

from lib_layered_config import cli


def _write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_cli_read_config_outputs_json(tmp_path: Path) -> None:
    etc_root = tmp_path / "etc"
    _write_toml(
        etc_root / "demo" / "config.toml",
        """[service]\ntimeout = 15\n""",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            "Acme",
            "--app",
            "Demo",
            "--slug",
            "demo",
            "--indent",
            "0",
        ],
        env={"LIB_LAYERED_CONFIG_ETC": str(etc_root)},
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["service"]["timeout"] == 15


def test_cli_read_config_with_provenance(tmp_path: Path) -> None:
    etc_root = tmp_path / "etc"
    _write_toml(
        etc_root / "demo" / "config.toml",
        """[feature]\nenabled = true\n""",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "read",
            "--vendor",
            "Acme",
            "--app",
            "Demo",
            "--slug",
            "demo",
            "--provenance",
        ],
        env={"LIB_LAYERED_CONFIG_ETC": str(etc_root)},
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
    etc_root = tmp_path / "etc"
    _write_toml(
        etc_root / "demo" / "config.toml",
        "value = 1\n",
    )
    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", str(etc_root))
    exit_code = cli.main(
        [
            "--traceback",
            "read",
            "--vendor",
            "Acme",
            "--app",
            "Demo",
            "--slug",
            "demo",
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
