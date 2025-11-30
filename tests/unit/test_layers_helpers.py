"""Unit poems that exercise internal helpers from ``lib_layered_config._layers``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib_layered_config._layers import (
    _default_snapshots,
    _load_entry,
    _note_layer_error,
    _paths_in_preferred_order,
    _snapshots_from_paths,
    merge_or_empty,
)
from tests.support.os_markers import os_agnostic


@os_agnostic
def test_merge_or_empty_reports_empty_when_no_layers() -> None:
    result = merge_or_empty([])
    assert result.data == {} and result.provenance == {}


@os_agnostic
def test_load_default_layer_skips_unknown_extension(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text("ignored", encoding="utf-8")
    assert list(_default_snapshots(str(path))) == []


@os_agnostic
def test_load_entry_returns_none_when_file_missing(tmp_path: Path) -> None:
    target = tmp_path / "absent.toml"
    assert _load_entry("defaults", str(target)) is None


@os_agnostic
def test_load_entry_ignores_empty_payload(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    assert _load_entry("defaults", str(path)) is None


@os_agnostic
def test_snapshots_from_paths_skip_entries_without_loaders(tmp_path: Path) -> None:
    stray = tmp_path / "orphan.ini"
    stray.write_text("ignored", encoding="utf-8")

    snapshots = list(_snapshots_from_paths("app", [str(stray)], None))

    assert snapshots == []


@os_agnostic
def test_paths_in_preferred_order_honours_declared_priority(tmp_path: Path) -> None:
    candidates = [
        str(tmp_path / "payload.json"),
        str(tmp_path / "payload.toml"),
        str(tmp_path / "payload.yaml"),
    ]

    ordered = _paths_in_preferred_order(candidates, ["yaml", "toml"])

    assert [Path(entry).suffix for entry in ordered] == [".yaml", ".toml", ".json"]


@os_agnostic
def test_note_layer_error_emits_event_with_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_log(event: str, **payload: object) -> None:
        captured["event"] = event
        captured["payload"] = payload

    monkeypatch.setattr("lib_layered_config._layers.log_debug", fake_log)

    _note_layer_error("user", "/tmp/config.toml", RuntimeError("boom"))

    assert captured == {
        "event": "layer_error",
        "payload": {"layer": "user", "path": "/tmp/config.toml", "error": "boom"},
    }
