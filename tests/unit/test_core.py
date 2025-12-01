"""Core orchestration tests rewritten as gentle prose."""

from __future__ import annotations

import pytest

import runpy
import sys

from lib_layered_config import core

from tests.support.os_markers import os_agnostic


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

    with pytest.raises(SystemExit) as captured:
        runpy.run_module("lib_layered_config.__main__", run_name="__main__")

    assert (captured.value.code, exit_marker) == (
        11,
        {"arguments": [], "restore_traceback": True},
    )
