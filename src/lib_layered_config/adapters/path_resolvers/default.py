"""Filesystem path resolution composed of small platform-specific verses.

Purpose
    Implement the :class:`lib_layered_config.application.ports.PathResolver`
    port while keeping operating-system branches readable and testable.

Contents
    - ``DefaultPathResolver``: public adapter consumed by the composition root.
    - ``_linux_paths`` / ``_mac_paths`` / ``_windows_paths``: platform poems that
      describe how each layer is built.
    - ``_dotenv_paths`` helpers: narrate how ``.env`` locations are discovered
      near the project root and within OS-specific config directories.
    - ``_collect_layer``: shared helper that enumerates canonical files within a
      base directory.

System Integration
    Produces ordered path lists for the core merge pipeline. All filesystem
    knowledge stays here so inner layers remain filesystem-agnostic.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Iterable, List

from ...observability import log_debug

#: Supported structured configuration file extensions used when expanding
#: ``config.d`` directories.
_ALLOWED_EXTENSIONS = (".toml", ".yaml", ".yml", ".json")


class DefaultPathResolver:
    """Resolve candidate paths for each configuration layer.

    Why
    ----
    Centralise path discovery so the composition root stays platform-agnostic
    and easy to test.
    """

    def __init__(
        self,
        *,
        vendor: str,
        app: str,
        slug: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        platform: str | None = None,
        hostname: str | None = None,
    ) -> None:
        """Store context required to resolve filesystem locations.

        Parameters
        ----------
        vendor / app / slug:
            Naming context injected into platform-specific directory structures.
        cwd:
            Working directory to use when searching for ``.env`` files.
        env:
            Optional environment mapping that overrides ``os.environ`` values
            (useful for deterministic tests).
        platform:
            Platform identifier (``sys.platform`` clone). Defaults to the
            current interpreter platform.
        hostname:
            Hostname used for host-specific configuration lookups.

        Side Effects
        ------------
        Reads from :mod:`os.environ` and :func:`socket.gethostname` to populate
        defaults.
        """

        self.vendor = vendor
        self.application = app
        self.slug = slug
        self.cwd = cwd or Path.cwd()
        self.env = {**os.environ, **(env or {})}
        self.platform = platform or sys.platform
        self.hostname = hostname or socket.gethostname()

    def app(self) -> Iterable[str]:
        """Return candidate system-wide configuration paths.

            Why
            ----
            Provide the lowest-precedence defaults shared across machines.

            Examples
            --------
            >>> import os
            >>> from tempfile import TemporaryDirectory
            >>> from pathlib import Path
        >>> import os
            >>> tmp = TemporaryDirectory()
            >>> root = Path(tmp.name)
            >>> target = root / "demo"
            >>> target.mkdir(parents=True, exist_ok=True)
            >>> config_body = os.linesep.join(['[settings]', 'value=1'])
            >>> _ = (target / "config.toml").write_text(config_body, encoding="utf-8")
            >>> resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", env={"LIB_LAYERED_CONFIG_ETC": str(root)}, platform="linux")
            >>> paths = list(resolver.app())
            >>> [Path(p).name for p in paths]
            ['config.toml']
            >>> tmp.cleanup()
        """

        return self._iter_layer("app")

    def host(self) -> Iterable[str]:
        """Return host-specific overrides.

        Why
        ----
        Allow operators to tailor configuration to individual hosts (e.g.
        `demo-host.toml`).
        """

        return self._iter_layer("host")

    def user(self) -> Iterable[str]:
        """Return user-level configuration locations.

        Why
        ----
        Capture per-user preferences stored in XDG/macOS/Windows user config
        directories.
        """

        return self._iter_layer("user")

    def dotenv(self) -> Iterable[str]:
        """Return candidate ``.env`` locations discovered during path resolution.

        Why
        ----
        `.env` files often live near the project root; this helper provides the
        ordered search list for the dotenv adapter.
        """

        return list(self._dotenv_paths())

    def _iter_layer(self, layer: str) -> Iterable[str]:
        """Dispatch to the platform-specific implementation for *layer*."""

        paths = self._platform_paths(layer)
        if paths:
            log_debug("path_candidates", layer=layer, path=None, count=len(paths))
        return paths

    def _platform_paths(self, layer: str) -> List[str]:
        """Return discovered paths for *layer* based on the current platform."""

        if self._is_linux:
            return list(self._linux_paths(layer))
        if self._is_macos:
            return list(self._mac_paths(layer))
        if self._is_windows:
            return list(self._windows_paths(layer))
        return []

    @property
    def _is_linux(self) -> bool:
        """Return ``True`` when running on a Linux platform.

        Why
        ----
        Determines which helper method to invoke during resolution.
        """

        return self.platform.startswith("linux")

    @property
    def _is_macos(self) -> bool:
        """Return ``True`` when running on macOS."""

        return self.platform == "darwin"

    @property
    def _is_windows(self) -> bool:
        """Return ``True`` when running on Windows."""

        return self.platform.startswith("win")

    def _linux_paths(self, layer: str) -> Iterable[str]:
        """Yield Linux-specific candidates for *layer*.

        Why
        ----
        Mirror the XDG specification and `/etc` conventions documented in the
        system design.
        """

        builders = {
            "app": self._linux_app_paths,
            "host": self._linux_host_paths,
            "user": self._linux_user_paths,
        }
        yield from builders.get(layer, lambda: [])()

    def _mac_paths(self, layer: str) -> Iterable[str]:
        """Yield macOS-specific candidates for *layer*.

        Why
        ----
        Follow macOS Application Support conventions for vendor/app directories.
        """

        builders = {
            "app": self._mac_app_paths,
            "host": self._mac_host_paths,
            "user": self._mac_user_paths,
        }
        yield from builders.get(layer, lambda: [])()

    def _windows_paths(self, layer: str) -> Iterable[str]:
        """Yield Windows-specific candidates for *layer*.

        Why
        ----
        Respect ProgramData/AppData directory layouts and allow overrides for
        portable setups.
        """

        builders = {
            "app": self._windows_app_paths,
            "host": self._windows_host_paths,
            "user": self._windows_user_paths,
        }
        yield from builders.get(layer, lambda: [])()

    def _linux_app_paths(self) -> Iterable[str]:
        etc_root = Path(self.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
        yield from _collect_layer(etc_root / self.slug)

    def _linux_host_paths(self) -> Iterable[str]:
        etc_root = Path(self.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
        candidate = etc_root / self.slug / "hosts" / f"{self.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def _linux_user_paths(self) -> Iterable[str]:
        xdg = self.env.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        yield from _collect_layer(base / self.slug)

    def _mac_app_paths(self) -> Iterable[str]:
        default_root = Path("/Library/Application Support")
        root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))
        yield from _collect_layer(root / self.vendor / self.application)

    def _mac_host_paths(self) -> Iterable[str]:
        default_root = Path("/Library/Application Support")
        root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))
        candidate = root / self.vendor / self.application / "hosts" / f"{self.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def _mac_user_paths(self) -> Iterable[str]:
        home_default = Path.home() / "Library/Application Support"
        home_root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))
        yield from _collect_layer(home_root / self.vendor / self.application)

    def _windows_app_paths(self) -> Iterable[str]:
        base = self._program_data_root() / self.vendor / self.application
        yield from _collect_layer(base)

    def _windows_host_paths(self) -> Iterable[str]:
        base = self._program_data_root() / self.vendor / self.application
        candidate = base / "hosts" / f"{self.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def _windows_user_paths(self) -> Iterable[str]:
        base = self._appdata_root() / self.vendor / self.application
        if not base.exists():
            base = self._localappdata_root() / self.vendor / self.application
        yield from _collect_layer(base)

    def _program_data_root(self) -> Path:
        return Path(self.env.get("LIB_LAYERED_CONFIG_PROGRAMDATA", self.env.get("ProgramData", r"C:\\ProgramData")))

    def _appdata_root(self) -> Path:
        return Path(
            self.env.get("LIB_LAYERED_CONFIG_APPDATA", self.env.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        )

    def _localappdata_root(self) -> Path:
        return Path(
            self.env.get(
                "LIB_LAYERED_CONFIG_LOCALAPPDATA",
                self.env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"),
            )
        )

    def _dotenv_paths(self) -> Iterable[str]:
        """Return candidate dotenv paths discovered via upward search and OS-specific directories.

        Why
        ----
        `.env` files may live near the project root or in configuration
        directories; both need to be considered to honour precedence rules.
        """

        yield from self._project_dotenv_paths()
        extra = self._platform_dotenv_path()
        if extra and extra.is_file():
            yield str(extra)

    def _project_dotenv_paths(self) -> Iterable[str]:
        seen: set[Path] = set()
        for directory in [self.cwd, *self.cwd.parents]:
            candidate = directory / ".env"
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.is_file():
                yield str(candidate)

    def _platform_dotenv_path(self) -> Path | None:
        if self._is_linux:
            base = Path(self.env.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            return base / self.slug / ".env"
        if self._is_macos:
            home_default = Path.home() / "Library/Application Support"
            home_root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))
            return home_root / self.vendor / self.application / ".env"
        if self._is_windows:
            return self._appdata_root() / self.vendor / self.application / ".env"
        return None


def _collect_layer(base: Path) -> Iterable[str]:
    """Yield canonical config files and ``config.d`` entries under *base*.

    Why
    ----
    Normalise discovery across operating systems while respecting preferred
    configuration formats.

    Parameters
    ----------
    base:
        Base directory for a particular layer.

    Returns
    -------
    Iterable[str]
        Absolute file paths discovered under ``base``.

    Examples
    --------
    >>> from tempfile import TemporaryDirectory
    >>> from pathlib import Path
    >>> import os
    >>> tmp = TemporaryDirectory()
    >>> root = Path(tmp.name)
    >>> file_a = root / 'config.toml'
    >>> file_b = root / 'config.d' / '10-extra.json'
    >>> file_b.parent.mkdir(parents=True, exist_ok=True)
    >>> _ = file_a.write_text(os.linesep.join(['[settings]', 'value=1']), encoding='utf-8')
    >>> _ = file_b.write_text('{"value": 2}', encoding='utf-8')
    >>> sorted(Path(p).name for p in _collect_layer(root))
    ['10-extra.json', 'config.toml']
    >>> tmp.cleanup()
    """

    config_file = base / "config.toml"
    if config_file.is_file():
        yield str(config_file)
    config_dir = base / "config.d"
    if config_dir.is_dir():
        for path in sorted(config_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in _ALLOWED_EXTENSIONS:
                yield str(path)
