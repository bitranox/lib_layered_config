from __future__ import annotations

import runpy
import sys
from typing import Any

from click.testing import CliRunner
import pytest

import lib_cli_exit_tools
from lib_layered_config import hello_world
from lib_layered_config import cli as cli_mod


def test_hello_world_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    hello_world()
    captured = capsys.readouterr()
    assert captured.out == "Hello World\n"
    assert captured.err == ""


def test_cli_info_command_sets_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []

    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)

    def record_traceback_flag() -> None:
        calls.append(lib_cli_exit_tools.config.traceback)

    monkeypatch.setattr(cli_mod.__init__conf__, "print_info", record_traceback_flag)

    result = cli_mod.main(["--traceback", "info"])

    assert result == 0
    assert calls == [True]
    assert lib_cli_exit_tools.config.traceback is False


def test_main_delegates_to_run_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[dict[str, Any]] = []

    def fake_run_cli(command, argv=None, *, prog_name=None, signal_specs=None, install_signals=True):
        recorded.append(
            {
                "command": command,
                "argv": argv,
                "prog_name": prog_name,
                "signal_specs": signal_specs,
                "install_signals": install_signals,
            }
        )
        return 42

    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", fake_run_cli)

    result = cli_mod.main(["info"])

    assert result == 42
    assert recorded == [
        {
            "command": cli_mod.cli,
            "argv": ["info"],
            "prog_name": cli_mod.__init__conf__.shell_command,
            "signal_specs": None,
            "install_signals": True,
        }
    ]


def test_module_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lib_layered_config.cli.main", lambda *_, **__: 0)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("lib_layered_config.__main__", run_name="__main__")

    assert exc.value.code == 0


def test_module_main_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error() -> int:
        raise RuntimeError("boom")

    signals: list[str] = []

    def fake_print(*, trace_back: bool = False, length_limit: int = 500, stream=None) -> None:
        signals.append("printed")
        assert trace_back is False
        assert length_limit == 500

    def fake_code(exc: BaseException) -> int:
        signals.append(f"code:{exc}")
        return 88

    monkeypatch.setattr("lib_layered_config.cli.main", lambda *_, **__: raise_error())
    monkeypatch.setattr(lib_cli_exit_tools, "print_exception_message", fake_print)
    monkeypatch.setattr(lib_cli_exit_tools, "get_system_exit_code", fake_code)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("lib_layered_config.__main__", run_name="__main__")

    assert exc.value.code == 88
    assert signals == ["printed", "code:boom"]


def test_module_main_traceback(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["lib_layered_config", "--traceback", "fail"])
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("lib_layered_config.__main__", run_name="__main__")

    captured = capsys.readouterr()

    assert exc.value.code != 0
    assert "Traceback (most recent call last)" in captured.err
    assert "RuntimeError: I should fail" in captured.err
    assert "[TRUNCATED" not in captured.err


def test_cli_without_subcommand_calls_domain_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def record_call() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "_domain_main", record_call)
    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, [])

    assert result.exit_code == 0
    assert calls == ["called"]
    assert result.output.strip() == ""


def test_main_without_subcommand_delegates_to_cli_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def record_call() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "_domain_main", record_call)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)

    def fake_run_cli(command, argv=None, *, prog_name=None, signal_specs=None, install_signals=True):
        runner = CliRunner()
        args = [] if argv is None else list(argv)
        result = runner.invoke(command, args)
        if result.exception is not None:
            raise result.exception
        return result.exit_code

    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", fake_run_cli)

    exit_code = cli_mod.main([])

    assert exit_code == 0
    assert calls == ["called"]


def test_cli_hello_and_fail_commands() -> None:
    runner = CliRunner()
    result_hello = runner.invoke(cli_mod.cli, ["hello"])
    assert result_hello.exit_code == 0
    assert result_hello.output.strip() == "Hello World"

    result_fail = runner.invoke(cli_mod.cli, ["fail"])
    assert result_fail.exit_code != 0
    assert isinstance(result_fail.exception, RuntimeError)
    assert str(result_fail.exception) == "I should fail"
