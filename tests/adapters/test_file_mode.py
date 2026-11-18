"""``apply_mode`` and ``modes_apply``: the chmod sink and the platform check, an adapter concern.

They lived in ``domain.permissions`` until 9.0.0; a chmod and an ``os.name`` read are filesystem and
platform I/O, which the domain layer does not do (user decision 2026-11-17, "Move, break in the
major").
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

import lib_layered_config.domain.permissions as domain_permissions
from lib_layered_config.adapters._file_mode import apply_mode, modes_apply
from lib_layered_config.domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path


@os_agnostic
def test_modes_apply_exactly_where_the_os_is_posix() -> None:
    assert modes_apply() is (os.name == "posix")


@os_agnostic
@pytest.mark.parametrize("name", ["apply_mode", "modes_apply"])
def test_the_domain_no_longer_carries_them(name: str) -> None:
    assert not hasattr(domain_permissions, name)
    assert name not in domain_permissions.__all__


@os_agnostic
def test_apply_mode_refuses_a_negative_mode_on_every_platform(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(DeployModeError, match=r"mode -1 is outside 0\.\.0o7777"):
        apply_mode(target, DeployMode(-1, ModeKind.FILE))


@posix_only
def test_apply_mode_leaves_the_mode_alone_when_it_refuses(tmp_path: Path) -> None:
    target = tmp_path / "conf"
    target.mkdir()
    target.chmod(0o700)
    with pytest.raises(DeployModeError, match=r"world write \(0o002\)"):
        apply_mode(target, DeployMode(0o777, ModeKind.DIRECTORY))
    assert (target.stat().st_mode & 0o7777) == 0o700


@posix_only
def test_apply_mode_sets_the_mode(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("x", encoding="utf-8")
    apply_mode(target, DeployMode(0o640, ModeKind.FILE))
    assert (target.stat().st_mode & 0o7777) == 0o640
