"""Tests for permission constants and utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lib_layered_config.domain.permissions import (
    DEFAULT_APP_DIR_MODE,
    DEFAULT_APP_FILE_MODE,
    DEFAULT_USER_DIR_MODE,
    DEFAULT_USER_FILE_MODE,
    LAYER_PERMISSIONS,
    set_custom_permissions,
    set_permissions,
)

from tests.support.os_markers import os_agnostic, posix_only


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
# set_permissions: POSIX behavior
# ---------------------------------------------------------------------------


@posix_only
class TestSetPermissionsPosix:
    """Test set_permissions function on POSIX systems."""

    def test_sets_app_layer_file_permissions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")

        set_permissions(test_file, "app", is_dir=False)

        assert (test_file.stat().st_mode & 0o777) == 0o644

    def test_sets_app_layer_dir_permissions(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "config"
        test_dir.mkdir()

        set_permissions(test_dir, "app", is_dir=True)

        assert (test_dir.stat().st_mode & 0o777) == 0o755

    def test_sets_host_layer_file_permissions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "host.toml"
        test_file.write_text("test")

        set_permissions(test_file, "host", is_dir=False)

        assert (test_file.stat().st_mode & 0o777) == 0o644

    def test_sets_host_layer_dir_permissions(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "hosts"
        test_dir.mkdir()

        set_permissions(test_dir, "host", is_dir=True)

        assert (test_dir.stat().st_mode & 0o777) == 0o755

    def test_sets_user_layer_file_permissions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")

        set_permissions(test_file, "user", is_dir=False)

        assert (test_file.stat().st_mode & 0o777) == 0o600

    def test_sets_user_layer_dir_permissions(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "config"
        test_dir.mkdir()

        set_permissions(test_dir, "user", is_dir=True)

        assert (test_dir.stat().st_mode & 0o777) == 0o700

    def test_unknown_layer_uses_app_defaults(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")

        set_permissions(test_file, "unknown", is_dir=False)

        assert (test_file.stat().st_mode & 0o777) == 0o644


# ---------------------------------------------------------------------------
# set_permissions: Windows behavior (mocked)
# ---------------------------------------------------------------------------


@os_agnostic
class TestSetPermissionsWindows:
    """Test set_permissions is a no-op on Windows."""

    def test_skips_on_windows(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")
        original_mode = test_file.stat().st_mode

        with patch("lib_layered_config.domain.permissions.os.name", "nt"):
            set_permissions(test_file, "app", is_dir=False)

        # Mode unchanged on Windows
        assert test_file.stat().st_mode == original_mode


# ---------------------------------------------------------------------------
# set_custom_permissions: POSIX behavior
# ---------------------------------------------------------------------------


@posix_only
class TestSetCustomPermissionsPosix:
    """Test set_custom_permissions function on POSIX systems."""

    def test_sets_custom_file_mode(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")

        set_custom_permissions(test_file, dir_mode=0o700, file_mode=0o600, is_dir=False)

        assert (test_file.stat().st_mode & 0o777) == 0o600

    def test_sets_custom_dir_mode(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "config"
        test_dir.mkdir()

        set_custom_permissions(test_dir, dir_mode=0o700, file_mode=0o600, is_dir=True)

        assert (test_dir.stat().st_mode & 0o777) == 0o700

    def test_skips_when_file_mode_is_none(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")
        original_mode = test_file.stat().st_mode

        set_custom_permissions(test_file, dir_mode=0o700, file_mode=None, is_dir=False)

        assert test_file.stat().st_mode == original_mode

    def test_skips_when_dir_mode_is_none(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "config"
        test_dir.mkdir()
        original_mode = test_dir.stat().st_mode

        set_custom_permissions(test_dir, dir_mode=None, file_mode=0o600, is_dir=True)

        assert test_dir.stat().st_mode == original_mode

    def test_skips_when_both_modes_are_none(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")
        original_mode = test_file.stat().st_mode

        set_custom_permissions(test_file, dir_mode=None, file_mode=None, is_dir=False)

        assert test_file.stat().st_mode == original_mode


# ---------------------------------------------------------------------------
# set_custom_permissions: Windows behavior (mocked)
# ---------------------------------------------------------------------------


@os_agnostic
class TestSetCustomPermissionsWindows:
    """Test set_custom_permissions is a no-op on Windows."""

    def test_skips_on_windows(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.toml"
        test_file.write_text("test")
        original_mode = test_file.stat().st_mode

        with patch("lib_layered_config.domain.permissions.os.name", "nt"):
            set_custom_permissions(test_file, dir_mode=0o700, file_mode=0o600, is_dir=False)

        # Mode unchanged on Windows
        assert test_file.stat().st_mode == original_mode


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
