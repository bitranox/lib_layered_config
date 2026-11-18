"""A dotenv load returns what it found, data and file together, and the loader keeps no state.

Until 9.0.0 the loader reported its file through a ``last_loaded_path`` attribute that each call
overwrote, so a load that raised could leave the previous call's path behind for the next reader
(DATA-PERF-REVIEW.md finding 9).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, cast

import pytest

from lib_layered_config import Layer, read_config_raw
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.application.ports import DotEnvLoad
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


@os_agnostic
def test_a_load_names_the_file_it_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DB__HOST=localhost\n", encoding="utf-8")

    loaded = DefaultDotEnvLoader().load(tmp_path)

    assert loaded == DotEnvLoad({"db": {"host": "localhost"}}, tmp_path / ".env")


@os_agnostic
def test_the_loader_keeps_no_state_between_loads(tmp_path: Path) -> None:
    good = tmp_path / "good.env"
    good.write_text("A=1\n", encoding="utf-8")
    bad = tmp_path / "bad.env"
    bad.write_text("NOT A LINE\n", encoding="utf-8")
    loader = DefaultDotEnvLoader()

    loader.load(dotenv_path=good)
    with pytest.raises(InvalidFormatError):
        loader.load(dotenv_path=bad)

    assert vars(loader).keys() == {"_extras", "_not_sensitive"}


@os_agnostic
def test_a_load_result_cannot_be_changed(tmp_path: Path) -> None:
    loaded = DefaultDotEnvLoader().load(tmp_path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cast("Any", loaded).path = tmp_path


@os_agnostic
def test_the_dotenv_layer_is_attributed_to_the_file_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_layered_sandbox(tmp_path / "layers", vendor="Acme", app="Demo", slug="demo").apply_env(monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("DB__HOST=localhost\n", encoding="utf-8")

    origin = read_config_raw(vendor="Acme", app="Demo", slug="demo", start_dir=str(project)).provenance["db.host"]

    assert (Layer(origin["layer"]), origin["path"]) == (Layer.DOTENV, str(project / ".env"))
