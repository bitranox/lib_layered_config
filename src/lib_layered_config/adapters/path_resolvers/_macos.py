"""macOS-specific path resolution strategy.

Purpose
    Implement path resolution following macOS Application Support conventions.

Contents
    - ``MacOSStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ._base import PlatformStrategy, collect_layer


class MacOSStrategy(PlatformStrategy):
    """Resolve paths following macOS Application Support conventions.

    Why
    ----
    Follow macOS conventions for vendor/app directories under
    ``/Library/Application Support`` and ``~/Library/Application Support``.

    Path Layouts
    ------------
    - App: ``/Library/Application Support/<Vendor>/<App>``
    - Host: ``<app>/hosts/<hostname>.toml``
    - User: ``~/Library/Application Support/<Vendor>/<App>``
    - Dotenv: ``~/Library/Application Support/<Vendor>/<App>/.env``
    """

    def _app_root(self) -> Path:
        """Return the base directory for system-wide Application Support.

        Returns
        -------
        Path
            ``/Library/Application Support`` or overridden root.
        """
        default_root = Path("/Library/Application Support")
        return Path(self.ctx.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))

    def _home_root(self) -> Path:
        """Return the base directory for user-level Application Support.

        Returns
        -------
        Path
            ``~/Library/Application Support`` or overridden root.
        """
        home_default = Path.home() / "Library/Application Support"
        return Path(self.ctx.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))

    def app_paths(self) -> Iterable[str]:
        """Yield macOS application-default configuration paths.

        Why
        ----
        Follow macOS Application Support directory conventions.

        Returns
        -------
        Iterable[str]
            Application-level configuration paths.
        """
        yield from collect_layer(self._app_root() / self.ctx.vendor / self.ctx.app)

    def host_paths(self) -> Iterable[str]:
        """Yield macOS host-specific configuration paths.

        Why
        ----
        Support host overrides stored under ``hosts/<hostname>.toml`` within
        Application Support.

        Returns
        -------
        Iterable[str]
            Host-level macOS configuration paths (empty when missing).
        """
        candidate = self._app_root() / self.ctx.vendor / self.ctx.app / "hosts" / f"{self.ctx.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def user_paths(self) -> Iterable[str]:
        """Yield macOS user-specific configuration paths.

        Why
        ----
        Honour per-user Application Support directories with optional overrides.

        Returns
        -------
        Iterable[str]
            User-level macOS configuration paths.
        """
        yield from collect_layer(self._home_root() / self.ctx.vendor / self.ctx.app)

    def dotenv_path(self) -> Path | None:
        """Return macOS-specific ``.env`` fallback path.

        Returns
        -------
        Path
            Path to ``~/Library/Application Support/<Vendor>/<App>/.env``.
        """
        return self._home_root() / self.ctx.vendor / self.ctx.app / ".env"
