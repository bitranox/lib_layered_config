"""Reading and deploying a ``.d`` directory use one order on every OS: the names' exact characters.

``Z.toml`` sorts before ``a-extra.toml`` (upper case first), so ``a-extra.toml`` wins a key both set,
on Windows as on Linux and macOS. Run on a Windows cell these fail with case-insensitive ordering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.deploy import deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


def _config_with_dot_d(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    base = directory / "config.toml"
    base.write_text("[service]\nname = 'base'\n", encoding="utf-8")
    dot_d = directory / "config.d"
    dot_d.mkdir()
    (dot_d / "a-extra.toml").write_text("[service]\nname = 'a-extra'\n", encoding="utf-8")
    (dot_d / "Z.toml").write_text("[service]\nname = 'Z'\n", encoding="utf-8")
    return base


@os_agnostic
def test_a_read_merges_dot_d_files_in_exact_name_order(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    defaults = _config_with_dot_d(tmp_path / "defaults")
    sandbox.start_dir.mkdir(parents=True, exist_ok=True)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, default_file=defaults, start_dir=sandbox.start_dir)

    assert config.get("service.name") == "a-extra"
    origin = config.origin("service.name")
    assert origin is not None
    assert origin["path"] is not None
    assert origin["path"].endswith("a-extra.toml")


@os_agnostic
def test_a_deploy_copies_dot_d_files_in_exact_name_order(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source = _config_with_dot_d(tmp_path / "source")

    (result,) = deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"], set_permissions=False)

    assert [copy.destination.name for copy in result.dot_d_results] == ["Z.toml", "a-extra.toml"]
