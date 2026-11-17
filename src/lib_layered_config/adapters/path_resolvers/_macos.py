"""macOS-specific path resolution strategy.

Implement path resolution following macOS Application Support conventions.

Contents:
    - ``MacOSStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._base import PlatformStrategy, home_directory, override_root

if TYPE_CHECKING:
    from collections.abc import Mapping


__all__ = [
    "MacOSStrategy",
    "mac_app_root",
    "mac_home_root",
]


def mac_app_root(env: Mapping[str, str]) -> Path:
    """``LIB_LAYERED_CONFIG_MAC_APP_ROOT`` when set, else ``/Library/Application Support``.

    Raises:
        LayerRootNotAbsoluteError: The override is empty or relative.
    """
    return override_root(env, "LIB_LAYERED_CONFIG_MAC_APP_ROOT", lambda: Path("/Library/Application Support"))


def mac_home_root(env: Mapping[str, str]) -> Path:
    """``LIB_LAYERED_CONFIG_MAC_HOME_ROOT`` when set, else ``~/Library/Application Support``.

    Raises:
        LayerRootNotAbsoluteError: The override is empty or relative.
    """
    return override_root(
        env, "LIB_LAYERED_CONFIG_MAC_HOME_ROOT", lambda: home_directory() / "Library/Application Support"
    )


class MacOSStrategy(PlatformStrategy):
    """Resolve paths following macOS Application Support conventions.

    Follow macOS conventions for vendor/app directories under
    ``/Library/Application Support`` and ``~/Library/Application Support``.

    Path Layouts:
        - App: ``/Library/Application Support/<Vendor>/<App>``
        - Host: ``<app>/hosts/<hostname>.toml``
        - User: ``~/Library/Application Support/<Vendor>/<App>``
        - Dotenv: ``~/Library/Application Support/<Vendor>/<App>/.env``
    """

    def _app_root(self) -> Path:
        """Return the base directory for system-wide Application Support.

        Returns:
            ``/Library/Application Support`` or overridden root.
        """
        return mac_app_root(self.ctx.env)

    def _home_root(self) -> Path:
        """Return the base directory for user-level Application Support.

        Returns:
            ``~/Library/Application Support`` or overridden root.
        """
        return mac_home_root(self.ctx.env)

    def app_dirs(self) -> tuple[Path, ...]:
        """Return ``/Library/Application Support/<Vendor>/<App>`` (or its overridden root).

        Returns:
            The one directory, the profile segment included.
        """
        return (self._app_root() / self.ctx.vendor / self.ctx.app / self._profile_segment(),)

    def user_dir(self) -> Path:
        """Return ``~/Library/Application Support/<Vendor>/<App>`` (or its overridden root).

        Returns:
            The directory, the profile segment included.
        """
        return self._home_root() / self.ctx.vendor / self.ctx.app / self._profile_segment()

    def dotenv_path(self) -> Path | None:
        """Return macOS-specific ``.env`` fallback path.

        Returns:
            Path to ``~/Library/Application Support/<Vendor>/<App>/.env``.
        """
        profile_seg = self._profile_segment()
        return self._home_root() / self.ctx.vendor / self.ctx.app / profile_seg / ".env"
