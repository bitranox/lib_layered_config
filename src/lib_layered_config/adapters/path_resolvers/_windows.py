"""Windows-specific path resolution strategy.

Implement path resolution following Windows ProgramData/AppData conventions.

UNC network paths (e.g., ``//server/share``) are supported via environment
variable overrides and handled natively by ``pathlib.Path``.

Contents:
    - ``WindowsStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ._base import PlatformStrategy, collect_layer


class WindowsStrategy(PlatformStrategy):
    """Resolve paths following Windows directory conventions.

    Respect ``%ProgramData%`` and ``%APPDATA%/%LOCALAPPDATA%`` layouts with
    override support for portable deployments.

    UNC network paths (e.g., ``//server/share``) are supported via environment
    variable overrides. Paths are handled natively by ``pathlib.Path``.

    Path Layouts:
        - App: ``%ProgramData%/<Vendor>/<App>`` (or UNC: ``//server/share/<Vendor>/<App>``)
        - Host: ``<app>/hosts/<hostname>.toml``
        - User: ``%APPDATA%/<Vendor>/<App>`` (fallback to ``%LOCALAPPDATA%``)
        - Dotenv: ``%APPDATA%/<Vendor>/<App>/.env``
    """

    def _program_data_root(self) -> Path:
        """Return the base directory for ProgramData lookups.

        Centralise overrides for ``%ProgramData%`` so tests can supply temporary
        roots. Accepts UNC paths (e.g., ``//server/share``) which are handled
        natively by ``pathlib.Path``.

        Returns:
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

        Support overrides in tests or portable deployments.

        Returns:
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

        Provide a deterministic fallback when ``%APPDATA%`` does not exist.

        Returns:
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

        Mirror ``%ProgramData%/<Vendor>/<App>`` layouts with override support.

        Returns:
            Application-level Windows configuration paths.
        """
        profile_seg = self._profile_segment()
        base = self._program_data_root() / self.ctx.vendor / self.ctx.app / profile_seg
        yield from collect_layer(base)

    def host_paths(self) -> Iterable[str]:
        """Yield Windows host-specific configuration paths.

        Enable host overrides within ``%ProgramData%/<Vendor>/<App>/hosts``.

        Returns:
            Host-level Windows configuration paths.
        """
        profile_seg = self._profile_segment()
        base = self._program_data_root() / self.ctx.vendor / self.ctx.app / profile_seg
        candidate = base / "hosts" / f"{self.ctx.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def user_paths(self) -> Iterable[str]:
        """Yield Windows user-specific configuration paths.

        Honour ``%APPDATA%`` with a fallback to ``%LOCALAPPDATA%`` for portable setups.

        Returns:
            User-level Windows configuration paths.
        """
        profile_seg = self._profile_segment()
        roaming_base = self._appdata_root() / self.ctx.vendor / self.ctx.app / profile_seg
        roaming_paths = list(collect_layer(roaming_base))
        if roaming_paths:
            yield from roaming_paths
            return

        local_base = self._localappdata_root() / self.ctx.vendor / self.ctx.app / profile_seg
        yield from collect_layer(local_base)

    def dotenv_path(self) -> Path | None:
        """Return Windows-specific ``.env`` fallback path.

        Returns:
            Path to ``%APPDATA%/<Vendor>/<App>/.env``.
        """
        profile_seg = self._profile_segment()
        return self._appdata_root() / self.ctx.vendor / self.ctx.app / profile_seg / ".env"
