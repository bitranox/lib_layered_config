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
from ...domain.printable import escape_controls
from .._path_probe import PathKind, kind_or_raise
from ._base import PlatformStrategy, collect_layer, home_directory

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping


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


def _root(env: Mapping[str, str], *, override: str, name: str, default: Callable[[], Path]) -> Path:
    """The ``LIB_LAYERED_CONFIG_*`` *override* if set, else the Windows variable *name*, else *default()*.

    *default* is called only when neither variable is set, so a set APPDATA needs no home directory.

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
        root = default() if value is None else Path(value)
    if not root.is_absolute():
        raise LayerRootNotAbsoluteError(
            f"The %{name}% root '{escape_controls(str(root))}' is not an absolute path on this system; set {override} "
            f"(or {name}) to an absolute path"
        )
    return root


def program_data_root(env: Mapping[str, str]) -> Path:
    """The ``%ProgramData%`` root: the override, else ``ProgramData`` in any case, else ``C:/ProgramData``."""
    return _root(
        env, override="LIB_LAYERED_CONFIG_PROGRAMDATA", name="ProgramData", default=lambda: Path(r"C:\ProgramData")
    )


def appdata_root(env: Mapping[str, str]) -> Path:
    """The ``%APPDATA%`` root: the override, else ``APPDATA`` in any case, else ``~/AppData/Roaming``."""
    return _root(
        env,
        override="LIB_LAYERED_CONFIG_APPDATA",
        name="APPDATA",
        default=lambda: home_directory() / "AppData" / "Roaming",
    )


def localappdata_root(env: Mapping[str, str]) -> Path:
    """The ``%LOCALAPPDATA%`` root: the override, else ``LOCALAPPDATA`` in any case, else ``~/AppData/Local``."""
    return _root(
        env,
        override="LIB_LAYERED_CONFIG_LOCALAPPDATA",
        name="LOCALAPPDATA",
        default=lambda: home_directory() / "AppData" / "Local",
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

    def _vendor_app(self, root: Path) -> Path:
        return root / self.ctx.vendor / self.ctx.app / self._profile_segment()

    def app_dirs(self) -> tuple[Path, ...]:
        """Return ``%ProgramData%/<Vendor>/<App>`` (or its overridden root, a UNC path included).

        Returns:
            The one directory, the profile segment included.
        """
        return (self._vendor_app(self._program_data_root()),)

    def user_dir(self) -> Path:
        """Return the user directory a deploy writes: ``%APPDATA%/<Vendor>/<App>``.

        ``%LOCALAPPDATA%`` stands in when the APPDATA directory does not exist and no
        ``LIB_LAYERED_CONFIG_APPDATA`` override names it; a named override is used as given.
        :meth:`user_paths` reads the same two places, so the file a deploy writes is read back.

        Returns:
            The directory, the profile segment included.
        """
        appdata = self._appdata_root()
        if "LIB_LAYERED_CONFIG_APPDATA" not in self.ctx.env and kind_or_raise(appdata) is PathKind.MISSING:
            return self._vendor_app(self._localappdata_root())
        return self._vendor_app(appdata)

    def user_paths(self) -> Iterable[str]:
        """Yield Windows user-specific configuration paths.

        The files under ``%APPDATA%/<Vendor>/<App>`` when it holds any, else those under
        ``%LOCALAPPDATA%/<Vendor>/<App>``. This asks what is THERE, where :meth:`user_dir` asks
        whether the APPDATA directory exists: a file deployed to either place is read back, and
        a roaming file the user added later wins over a local one.

        Returns:
            User-level Windows configuration paths.
        """
        roaming_paths = list(collect_layer(self._vendor_app(self._appdata_root())))
        if roaming_paths:
            yield from roaming_paths
            return
        yield from collect_layer(self._vendor_app(self._localappdata_root()))

    def dotenv_path(self) -> Path | None:
        """Return Windows-specific ``.env`` fallback path.

        Returns:
            Path to ``%APPDATA%/<Vendor>/<App>/.env``.
        """
        profile_seg = self._profile_segment()
        return self._appdata_root() / self.ctx.vendor / self.ctx.app / profile_seg / ".env"
