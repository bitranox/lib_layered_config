"""Core orchestration tests rewritten as gentle prose."""

from __future__ import annotations

import logging
import runpy
import sys
from typing import TYPE_CHECKING

import lib_cli_exit_tools
import pytest

from lib_layered_config import core
from lib_layered_config.observability import TRACE_ID, bind_trace_id
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox


@os_agnostic
def test_read_config_raw_wraps_invalid_format_in_layer_error(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    broken = tmp_path / "defaults.toml"
    broken.write_text("not = ['valid'", encoding="utf-8")

    with pytest.raises(core.LayerLoadError) as captured:
        # start_dir under tmp_path keeps the .env search away from the repository's own .env.
        core.read_config_raw(vendor="Acme", app="Demo", slug="demo", default_file=broken, start_dir=str(tmp_path))

    assert isinstance(captured.value.__cause__, core.InvalidFormatError)
    assert "is not valid TOML" in str(captured.value)


@os_agnostic
def test_read_config_json_honours_indent_argument(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.json"
    defaults.write_text('{"service": {"port": 8080}}', encoding="utf-8")

    payload = core.read_config_json(
        vendor="Acme",
        app="Demo",
        slug="demo",
        default_file=defaults,
        indent=2,
    )

    assert '\n  "config"' in payload


@os_agnostic
def test_read_config_returns_empty_config_when_nothing_found(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    start = tmp_path / "empty"
    start.mkdir()

    result = core.read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(start))

    assert result is core.EMPTY_CONFIG


@os_agnostic
def test_every_read_takes_start_dir_as_a_path(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The docs type start_dir as str | Path | None for all three reads; read_config_json was the only
    # one annotated so, so a type checker refused a Path given to read_config or read_config_raw.
    sandbox.apply_env(monkeypatch)
    project = tmp_path / "project"
    (project / "sub").mkdir(parents=True)
    (project / ".env").write_text("SERVICE__TIMEOUT=7\n", encoding="utf-8")
    start = project / "sub"

    config = core.read_config(vendor="Acme", app="Demo", slug="demo", start_dir=start)
    raw = core.read_config_raw(vendor="Acme", app="Demo", slug="demo", start_dir=start)
    payload = core.read_config_json(vendor="Acme", app="Demo", slug="demo", start_dir=start)

    assert config.get("service.timeout") == 7
    assert raw.data == {"service": {"timeout": 7}}
    assert '"timeout":7' in payload


def _run_as_main(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> int | str | None:
    """Run ``python -m lib_layered_config`` in-process and return its exit code."""
    monkeypatch.setattr(sys, "argv", ["lib_layered_config", *arguments])
    # Another test may have imported the module already; runpy then warns that re-running it as
    # __main__ "may result in unpredictable behaviour". Run it from a clean slate instead.
    monkeypatch.delitem(sys.modules, "lib_layered_config.__main__", raising=False)
    with pytest.raises(SystemExit) as captured:
        runpy.run_module("lib_layered_config.__main__", run_name="__main__")
    return captured.value.code


@os_agnostic
def test_module_entry_runs_the_cli_and_restores_the_traceback_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    previous = lib_cli_exit_tools.config.traceback

    exit_code = _run_as_main(monkeypatch, "--traceback", "info")

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("Info for lib_layered_config:")
    assert lib_cli_exit_tools.config.traceback == previous


@os_agnostic
def test_module_entry_exits_with_the_cli_usage_status(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_as_main(monkeypatch, "read") == 2


def _read_sandbox_config(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> list[logging.LogRecord]:
    """Read a one-file sandbox config and return the library's own log records."""
    sandbox.apply_env(monkeypatch)
    sandbox.write("app", "config.toml", content="[service]\nport = 1\n")
    caplog.set_level(logging.DEBUG, logger="lib_layered_config")
    # start_dir under tmp_path keeps the .env search away from the repository's own .env.
    core.read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(tmp_path))
    records = [record for record in caplog.records if record.name == "lib_layered_config"]
    assert records, "liveness: read_config logged nothing, so no trace id could be checked"
    return records


@os_agnostic
def test_read_config_tags_its_events_with_the_callers_trace_id(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bind_trace_id("caller-trace")
    records = _read_sandbox_config(sandbox, monkeypatch, tmp_path, caplog)
    assert {record.__dict__["context"]["trace_id"] for record in records} == {"caller-trace"}


@os_agnostic
def test_the_callers_trace_id_survives_read_config(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bind_trace_id("caller-trace")
    _read_sandbox_config(sandbox, monkeypatch, tmp_path, caplog)
    assert TRACE_ID.get() == "caller-trace"


@os_agnostic
def test_read_config_binds_no_trace_id_of_its_own(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    records = _read_sandbox_config(sandbox, monkeypatch, tmp_path, caplog)
    assert {record.__dict__["context"]["trace_id"] for record in records} == {None}
