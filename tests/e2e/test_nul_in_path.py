"""A path holding a NUL character gets the documented refusal, never a bare ``ValueError``.

No file can have such a name, and ``os.stat`` refuses it with ``ValueError`` before asking the OS.
The read functions already turned that into ``LayerLoadError``; a deploy source and a generate
destination let it escape as a ``ValueError`` no caller catching the documented errors expected
(user decision 2026-11-17: "Accept types, refuse NUL"). A NUL is a ``str`` a correctly typed
caller can pass straight from user input, unlike a wrong type, which pyright flags.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import (
    GenerateDestinationError,
    LayerLoadError,
    deploy_config,
    deploy_config_paths,
    generate_examples,
    read_config,
    read_deploy_config,
)
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.support import LayeredSandbox

NUL_PATH = "conf" + chr(0) + "ig.toml"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path / "root", vendor="Acme", app="Demo", slug="demo")
    created.apply_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    return created


def _deploy() -> object:
    return deploy_config(NUL_PATH, vendor="Acme", app="Demo", slug="demo", targets=["user"])


def _deploy_paths() -> object:
    return deploy_config_paths(NUL_PATH, vendor="Acme", app="Demo", slug="demo", targets=["user"])


def _read_deploy() -> object:
    return read_deploy_config(NUL_PATH, vendor="Acme", app="Demo", slug="demo", skip=())


@os_agnostic
@pytest.mark.usefixtures("sandbox")
@pytest.mark.parametrize("call", [_deploy, _deploy_paths, _read_deploy], ids=["deploy", "paths", "read-deploy"])
def test_a_deploy_source_holding_a_nul_is_refused_as_not_found(call: Callable[[], object]) -> None:
    with pytest.raises(FileNotFoundError) as caught:
        call()

    message = str(caught.value)
    assert message == "Configuration source not found: conf\\u0000ig.toml"


@os_agnostic
@pytest.mark.usefixtures("sandbox")
def test_a_generate_destination_holding_a_nul_is_refused_naming_it(tmp_path: Path) -> None:
    with pytest.raises(GenerateDestinationError) as caught:
        generate_examples(tmp_path / NUL_PATH, vendor="Acme", app="Demo", slug="demo")

    message = str(caught.value)
    assert chr(0) not in message
    assert "conf\\u0000ig.toml" in message
    assert "cannot be created" in message


@os_agnostic
@pytest.mark.usefixtures("sandbox")
def test_a_named_read_file_holding_a_nul_stays_a_layer_load_error() -> None:
    # The control: the read side already refused it with its documented error.
    with pytest.raises(LayerLoadError):
        read_config(vendor="Acme", app="Demo", slug="demo", default_file=NUL_PATH)
