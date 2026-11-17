"""A deploy into a layer directory that is a symbolic link leaves the link's target mode alone.

A user often links ``~/.config/<app>`` to a dotfiles checkout or a shared directory. Deploy wrote the
file through the link, as it should, and then set the layer's directory mode on the directory deploy
hardens, which ``chmod`` resolved to the link's TARGET: a shared 0755 directory became 0700 (and on the
app and host layers a 0750 one would become 0755). Deploy now writes through the link as before, gives
the file its mode, and leaves the target directory's mode as it found it, logging that it did.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.deploy import DeployAction, deploy_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Linked"
SLUG = "linked"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    home = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    return home


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.toml"
    path.write_text("[service]\nflag = true\n", encoding="utf-8")
    return path


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777


def _link_user_layer(sandbox: LayeredSandbox, tmp_path: Path) -> Path:
    """Make the user layer directory a link to a 0755 directory elsewhere and return that directory."""
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o755)
    layer = sandbox.roots["user"]
    layer.parent.mkdir(parents=True, exist_ok=True)
    layer.symlink_to(shared, target_is_directory=True)
    return shared


def _deploy(source: Path, *, force: bool = False, batch: bool = False) -> list[object]:
    return list(deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"], force=force, batch=batch))


@posix_only
def test_a_created_file_goes_through_the_link_and_the_target_keeps_its_mode(
    sandbox: LayeredSandbox, source: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    shared = _link_user_layer(sandbox, tmp_path)
    caplog.set_level(logging.WARNING, logger="lib_layered_config")

    (result,) = deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"])

    assert result.action == DeployAction.CREATED
    assert (shared / "config.toml").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert _mode(shared) == 0o755
    assert _mode(shared / "config.toml") == 0o600
    (record,) = [record for record in caplog.records if record.message == "deploy_directory_mode_skipped"]
    assert record.__dict__["context"]["path"] == str(sandbox.roots["user"])


@posix_only
def test_an_overwrite_and_a_ucf_through_the_link_leave_the_target_mode_alone(
    sandbox: LayeredSandbox, source: Path, tmp_path: Path
) -> None:
    shared = _link_user_layer(sandbox, tmp_path)
    (shared / "config.toml").write_text("[service]\nflag = false\n", encoding="utf-8")

    _deploy(source, force=True)
    assert _mode(shared) == 0o755
    (shared / "config.toml").write_text("[service]\nflag = false\n", encoding="utf-8")
    _deploy(source, batch=True)

    assert _mode(shared) == 0o755
    assert [path.name for path in sorted(shared.glob("config.toml*.ucf"))] != []


@posix_only
def test_a_real_layer_directory_is_still_hardened(sandbox: LayeredSandbox, source: Path) -> None:
    layer = sandbox.roots["user"]
    layer.mkdir(parents=True, exist_ok=True)
    layer.chmod(0o755)

    _deploy(source)

    assert _mode(layer) == 0o700
