"""Tests for permission constants and utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config.domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from lib_layered_config.domain.permissions import (
    DEFAULT_APP_DIR_MODE,
    DEFAULT_APP_FILE_MODE,
    DEFAULT_USER_DIR_MODE,
    DEFAULT_USER_FILE_MODE,
    LAYER_PERMISSIONS,
    apply_mode,
)
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Permission constant values
# ---------------------------------------------------------------------------


@os_agnostic
class TestPermissionConstants:
    """Test permission constant values."""

    def test_app_dir_mode_is_755(self) -> None:
        assert DEFAULT_APP_DIR_MODE == 0o755

    def test_app_file_mode_is_644(self) -> None:
        assert DEFAULT_APP_FILE_MODE == 0o644

    def test_user_dir_mode_is_700(self) -> None:
        assert DEFAULT_USER_DIR_MODE == 0o700

    def test_user_file_mode_is_600(self) -> None:
        assert DEFAULT_USER_FILE_MODE == 0o600

    def test_layer_permissions_has_app_layer(self) -> None:
        assert "app" in LAYER_PERMISSIONS
        assert LAYER_PERMISSIONS["app"]["dir"] == 0o755
        assert LAYER_PERMISSIONS["app"]["file"] == 0o644

    def test_layer_permissions_has_host_layer(self) -> None:
        assert "host" in LAYER_PERMISSIONS
        assert LAYER_PERMISSIONS["host"]["dir"] == 0o755
        assert LAYER_PERMISSIONS["host"]["file"] == 0o644

    def test_layer_permissions_has_user_layer(self) -> None:
        assert "user" in LAYER_PERMISSIONS
        assert LAYER_PERMISSIONS["user"]["dir"] == 0o700
        assert LAYER_PERMISSIONS["user"]["file"] == 0o600


# ---------------------------------------------------------------------------
# apply_mode: Guarded chmod sink
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Public API exports
# ---------------------------------------------------------------------------


@os_agnostic
class TestPublicApiExports:
    """Test that permission constants are exported from the public API."""

    def test_exports_default_app_dir_mode(self) -> None:
        from lib_layered_config import DEFAULT_APP_DIR_MODE

        assert DEFAULT_APP_DIR_MODE == 0o755

    def test_exports_default_app_file_mode(self) -> None:
        from lib_layered_config import DEFAULT_APP_FILE_MODE

        assert DEFAULT_APP_FILE_MODE == 0o644

    def test_exports_default_user_dir_mode(self) -> None:
        from lib_layered_config import DEFAULT_USER_DIR_MODE

        assert DEFAULT_USER_DIR_MODE == 0o700

    def test_exports_default_user_file_mode(self) -> None:
        from lib_layered_config import DEFAULT_USER_FILE_MODE

        assert DEFAULT_USER_FILE_MODE == 0o600


# ---------------------------------------------------------------------------
# The removed setters
# ---------------------------------------------------------------------------


@os_agnostic
@pytest.mark.parametrize("name", ["set_permissions", "set_custom_permissions"])
def test_the_removed_setters_are_gone_from_the_permissions_module(name: str) -> None:
    from lib_layered_config.domain import permissions

    assert not hasattr(permissions, name)
    assert name not in permissions.__all__
