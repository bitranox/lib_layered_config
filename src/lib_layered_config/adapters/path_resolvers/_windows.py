"""Windows-specific path resolution strategy.

Implement path resolution following Windows ProgramData/AppData conventions.

UNC network paths (e.g., ``//server/share``) are supported via environment
variable overrides and handled natively by ``pathlib.Path``.

Contents:
    - ``WindowsStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.errors import LayerRootNotAbsoluteError
from ._base import PlatformStrategy, collect_layer, config_path_present

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


__all__ = [
    "WindowsStrategy",
    "appdata_root",
    "localappdata_root",
    "program_data_root",
    "windows_env_value",
]


def windows_env_value(env: Mapping[str, str], name: str) -> str | None:
    """Return the value of the Windows variable *name* in *env*, matching the name case-insensitively.

    Windows ignores case in variable names, and a ``dict`` copy of ``os.environ`` holds them
    uppercased (measured: ``"ProgramData"`` is in ``os.environ`` there but not in
    ``dict(os.environ)``, which has ``"PROGRAMDATA"``). The exact spelling wins when a caller's
    own mapping holds several.

    Examples:
        >>> windows_env_value({"PROGRAMDATA": "D:/Data"}, "ProgramData")
        'D:/Data'
        >>> windows_env_value({}, "APPDATA") is None
        True
    """
    if name in env:
        return env[name]
    folded = name.casefold()
    return next((value for key, value in env.items() if key.casefold() == folded), None)


def _root(env: Mapping[str, str], *, override: str, name: str, default: Path) -> Path:
    """The ``LIB_LAYERED_CONFIG_*`` *override* if set, else the Windows variable *name*, else *default*.

    Raises:
        LayerRootNotAbsoluteError: The chosen root is not absolute on this system (a
            ``ValidationError``). ``C:\\ProgramData`` is relative off Windows, and a relative value
            from the environment is relative everywhere; either would make every layer path, and
            every deploy, land under the current working directory.
    """
    if override in env:
        root = Path(env[override])
    else:
        value = windows_env_value(env, name)
        root = default if value is None else Path(value)
    if not root.is_absolute():
        raise LayerRootNotAbsoluteError(
            f"The %{name}% root {str(root)!r} is not an absolute path on this system; set {override} "
            f"(or {name}) to an absolute path"
        )
    return root


def program_data_root(env: Mapping[str, str]) -> Path:
    """The ``%ProgramData%`` root: the override, else ``ProgramData`` in any case, else ``C:/ProgramData``."""
    return _root(env, override="LIB_LAYERED_CONFIG_PROGRAMDATA", name="ProgramData", default=Path(r"C:\ProgramData"))


def appdata_root(env: Mapping[str, str]) -> Path:
    """The ``%APPDATA%`` root: the override, else ``APPDATA`` in any case, else ``~/AppData/Roaming``."""
    return _root(
        env, override="LIB_LAYERED_CONFIG_APPDATA", name="APPDATA", default=Path.home() / "AppData" / "Roaming"
    )


def localappdata_root(env: Mapping[str, str]) -> Path:
    """The ``%LOCALAPPDATA%`` root: the override, else ``LOCALAPPDATA`` in any case, else ``~/AppData/Local``."""
    return _root(
        env, override="LIB_LAYERED_CONFIG_LOCALAPPDATA", name="LOCALAPPDATA", default=Path.home() / "AppData" / "Local"
    )


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
        return program_data_root(self.ctx.env)

    def _appdata_root(self) -> Path:
        """Return the user AppData root used for ``%APPDATA%`` lookups.

        Support overrides in tests or portable deployments.

        Returns:
            Resolved AppData root directory.
        """
        return appdata_root(self.ctx.env)

    def _localappdata_root(self) -> Path:
        """Return the fallback LocalAppData root.

        Provide a deterministic fallback when ``%APPDATA%`` does not exist.

        Returns:
            Resolved LocalAppData root directory.
        """
        return localappdata_root(self.ctx.env)

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
        if config_path_present(candidate):
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
