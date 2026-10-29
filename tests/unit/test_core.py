"""Core orchestration tests rewritten as gentle prose."""

from __future__ import annotations

import logging
import runpy
import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import core
from lib_layered_config.observability import TRACE_ID, bind_trace_id
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox


@os_agnostic
def test_read_config_raw_wraps_invalid_format_in_layer_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_invalid(**_: object) -> None:  # pragma: no cover - executed via wrapper
        raise core.InvalidFormatError("bad payload")

    monkeypatch.setattr(core, "collect_layers", raise_invalid)

    with pytest.raises(core.LayerLoadError) as captured:
        core.read_config_raw(vendor="Acme", app="Demo", slug="demo", default_file=None)

    assert "bad payload" in str(captured.value)


@os_agnostic
def test_read_config_json_honours_indent_argument(tmp_path) -> None:
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
def test_read_config_returns_empty_config_when_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from lib_layered_config.application.merge import MergeResult

    monkeypatch.setattr(core, "read_config_raw", lambda **_: MergeResult(data={}, provenance={}))

    result = core.read_config(vendor="Acme", app="Demo", slug="demo")

    assert result is core.EMPTY_CONFIG


@os_agnostic
def test_module_entry_exits_with_cli_status(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_marker: dict[str, object] = {}

    def fake_main(arguments, restore_traceback):
        exit_marker["arguments"] = arguments
        exit_marker["restore_traceback"] = restore_traceback
        return 11

    monkeypatch.setattr("lib_layered_config.cli.main", fake_main)

    monkeypatch.setattr(sys, "argv", ["lib_layered_config"])
    # Another test may have imported the module already; runpy then warns that re-running it as
    # __main__ "may result in unpredictable behaviour". Run it from a clean slate instead.
    monkeypatch.delitem(sys.modules, "lib_layered_config.__main__", raising=False)

    with pytest.raises(SystemExit) as captured:
        runpy.run_module("lib_layered_config.__main__", run_name="__main__")

    assert (captured.value.code, exit_marker) == (
        11,
        {"arguments": [], "restore_traceback": True},
    )


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
