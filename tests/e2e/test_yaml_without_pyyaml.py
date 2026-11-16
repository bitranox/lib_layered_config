"""A YAML configuration file on a host without PyYAML is refused, naming the extra that reads it.

PyYAML ships only in the ``yaml`` extra, and such a file used to be skipped without a word, so its
settings silently did not apply and a deploy installed a ``.d`` YAML file nobody had parsed.
User decision 2026-11-16 (R5-F1, "Refuse, name the extra"): every read and deploy raises
``LayerLoadError`` naming the file and ``lib_layered_config[yaml]``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.deploy import deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.layered import LayeredSandbox

_EXTRA = "lib_layered_config[yaml]"


@pytest.fixture
def without_pyyaml(monkeypatch: pytest.MonkeyPatch) -> None:
    # PyYAML is a third-party import at the edge of the loader: a None entry in sys.modules makes
    # `import yaml` raise ModuleNotFoundError as on a host without it, and the loader's module-level
    # cache is cleared so an earlier test's import does not answer.
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(structured_module, "yaml", None)


def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    sandbox = create_layered_sandbox(tmp_path / "root", vendor="Acme", app="Demo", slug="demo")
    sandbox.apply_env(monkeypatch)
    return sandbox


@os_agnostic
@pytest.mark.usefixtures("without_pyyaml")
def test_a_yaml_default_file_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch)
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("a: 1\n", encoding="utf-8")

    with pytest.raises(LayerLoadError) as caught:
        read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(sandbox.start_dir), default_file=defaults)

    assert str(defaults) in str(caught.value)
    assert _EXTRA in str(caught.value)


@os_agnostic
@pytest.mark.usefixtures("without_pyyaml")
def test_a_yaml_file_in_a_layer_dot_d_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch)
    sandbox.write("user", "config.toml", content="c = 3\n")
    piece = sandbox.write("user", "config.d/10-log.yaml", content="b: 2\n")

    with pytest.raises(LayerLoadError) as caught:
        read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(sandbox.start_dir))

    assert str(piece) in str(caught.value)
    assert _EXTRA in str(caught.value)


@os_agnostic
@pytest.mark.usefixtures("without_pyyaml")
def test_toml_layers_still_read_without_pyyaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch)
    sandbox.write("user", "config.toml", content="c = 3\n")
    sandbox.write("user", "config.d/10-db.toml", content="b = 2\n")

    config = read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(sandbox.start_dir))

    assert config.as_dict() == {"c": 3, "b": 2}


@os_agnostic
@pytest.mark.usefixtures("without_pyyaml")
def test_deploy_refuses_a_yaml_dot_d_file_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch)
    source = tmp_path / "src" / "config.toml"
    (source.parent / "config.d").mkdir(parents=True)
    source.write_text("c = 3\n", encoding="utf-8")
    piece = source.parent / "config.d" / "10-log.yaml"
    piece.write_text("b: 2\n", encoding="utf-8")

    with pytest.raises(LayerLoadError) as caught:
        deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], set_permissions=False)

    assert str(piece) in str(caught.value)
    assert _EXTRA in str(caught.value)
    assert not (sandbox.roots["user"] / "config.toml").exists()
