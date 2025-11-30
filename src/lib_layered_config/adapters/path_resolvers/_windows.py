"""Windows-specific path resolution strategy.

Purpose
    Implement path resolution following Windows ProgramData/AppData conventions.

Contents
    - ``WindowsStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ._base import PlatformStrategy, collect_layer


class WindowsStrategy(PlatformStrategy):
    """Resolve paths following Windows directory conventions.

    Why
    ----
    Respect ``%ProgramData%`` and ``%APPDATA%/%LOCALAPPDATA%`` layouts with
    override support for portable deployments.

    Path Layouts
    ------------
    - App: ``%ProgramData%/<Vendor>/<App>``
    - Host: ``<app>/hosts/<hostname>.toml``
    - User: ``%APPDATA%/<Vendor>/<App>`` (fallback to ``%LOCALAPPDATA%``)
    - Dotenv: ``%APPDATA%/<Vendor>/<App>/.env``
    """

    def _program_data_root(self) -> Path:
        """Return the base directory for ProgramData lookups.

        Why
        ----
        Centralise overrides for ``%ProgramData%`` so tests can supply temporary roots.

        Returns
        -------
        Path
            Resolved ProgramData root directory.
        """
        return Path(
            self.ctx.env.get(
                "LIB_LAYERED_CONFIG_PROGRAMDATA",
                self.ctx.env.get("ProgramData", r"C:\ProgramData"),
            )
        )

    def _appdata_root(self) -> Path:
        """Return the user AppData root used for ``%APPDATA%`` lookups.

        Why
        ----
        Support overrides in tests or portable deployments.

        Returns
        -------
        Path
            Resolved AppData root directory.
        """
        return Path(
            self.ctx.env.get(
                "LIB_LAYERED_CONFIG_APPDATA",
                self.ctx.env.get("APPDATA", Path.home() / "AppData" / "Roaming"),
            )
        )

    def _localappdata_root(self) -> Path:
        """Return the fallback LocalAppData root.

        Why
        ----
        Provide a deterministic fallback when ``%APPDATA%`` does not exist.

        Returns
        -------
        Path
            Resolved LocalAppData root directory.
        """
        return Path(
            self.ctx.env.get(
                "LIB_LAYERED_CONFIG_LOCALAPPDATA",
                self.ctx.env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"),
            )
        )

    def app_paths(self) -> Iterable[str]:
        """Yield Windows application-default configuration paths.

        Why
        ----
        Mirror ``%ProgramData%/<Vendor>/<App>`` layouts with override support.

        Returns
        -------
        Iterable[str]
            Application-level Windows configuration paths.
        """
        base = self._program_data_root() / self.ctx.vendor / self.ctx.app
        yield from collect_layer(base)

    def host_paths(self) -> Iterable[str]:
        """Yield Windows host-specific configuration paths.

        Why
        ----
        Enable host overrides within ``%ProgramData%/<Vendor>/<App>/hosts``.

        Returns
        -------
        Iterable[str]
            Host-level Windows configuration paths.
        """
        base = self._program_data_root() / self.ctx.vendor / self.ctx.app
        candidate = base / "hosts" / f"{self.ctx.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def user_paths(self) -> Iterable[str]:
        """Yield Windows user-specific configuration paths.

        Why
        ----
        Honour ``%APPDATA%`` with a fallback to ``%LOCALAPPDATA%`` for portable setups.

        Returns
        -------
        Iterable[str]
            User-level Windows configuration paths.
        """
        roaming_base = self._appdata_root() / self.ctx.vendor / self.ctx.app
        roaming_paths = list(collect_layer(roaming_base))
        if roaming_paths:
            yield from roaming_paths
            return

        local_base = self._localappdata_root() / self.ctx.vendor / self.ctx.app
        yield from collect_layer(local_base)

    def dotenv_path(self) -> Path | None:
        """Return Windows-specific ``.env`` fallback path.

        Returns
        -------
        Path
            Path to ``%APPDATA%/<Vendor>/<App>/.env``.
        """
        return self._appdata_root() / self.ctx.vendor / self.ctx.app / ".env"
