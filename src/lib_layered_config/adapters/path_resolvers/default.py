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
"""File suffixes considered when expanding ``config.d`` directories.

Why
----
Ensure platform-specific discovery yields consistent formats and avoids
non-structured files.

What
----
Tuple of lowercase extensions in precedence order.
"""


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

        What
        ----
        Delegates to :meth:`_iter_layer` with the ``"app"`` label so platform
        helpers can enumerate canonical locations.

        Returns
        -------
        Iterable[str]
            Ordered path strings for the application defaults layer.

        Examples
        --------
        >>> import os
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> tmp = TemporaryDirectory()
        >>> root = Path(tmp.name)
        >>> (root / 'demo').mkdir(parents=True, exist_ok=True)
        >>> body = os.linesep.join(['[settings]', 'value=1'])
        >>> _ = (root / 'demo' / 'config.toml').write_text(body, encoding='utf-8')
        >>> resolver = DefaultPathResolver(vendor='Acme', app='Demo', slug='demo', env={'LIB_LAYERED_CONFIG_ETC': str(root)}, platform='linux')
        >>> [Path(p).name for p in resolver.app()]
        ['config.toml']
        >>> tmp.cleanup()
        """

        return self._iter_layer("app")

    def host(self) -> Iterable[str]:
        """Return host-specific overrides.

        Why
        ----
        Allow operators to tailor configuration to individual hosts (e.g.
        ``demo-host.toml``).

        What
        ----
        Delegates to :meth:`_iter_layer` with the ``"host"`` label to collect
        hostname-specific files.

        Returns
        -------
        Iterable[str]
            Ordered host-level configuration paths.
        """

        return self._iter_layer("host")

    def user(self) -> Iterable[str]:
        """Return user-level configuration locations.

        Why
        ----
        Capture per-user preferences stored in XDG/macOS/Windows user config
        directories.

        What
        ----
        Delegates to :meth:`_iter_layer` with the ``"user"`` label, leveraging
        platform helpers to enumerate per-user directories.

        Returns
        -------
        Iterable[str]
            Ordered user-level configuration paths.
        """

        return self._iter_layer("user")

    def dotenv(self) -> Iterable[str]:
        """Return candidate ``.env`` locations discovered during path resolution.

        Why
        ----
        `.env` files often live near the project root; this helper provides the
        ordered search list for the dotenv adapter.

        What
        ----
        Materialises the iterator produced by :meth:`_dotenv_paths` so callers
        can inspect the ordered candidates.

        Returns
        -------
        Iterable[str]
            Ordered `.env` path strings.
        """

        return list(self._dotenv_paths())

    def _iter_layer(self, layer: str) -> Iterable[str]:
        """Dispatch to the platform-specific implementation for *layer*.

        Why
        ----
        Centralises logging and platform dispatch so public helpers stay tiny.

        What
        ----
        Delegates to :meth:`_platform_paths`, emits a debug event when candidates
        exist, and returns the resulting iterable.

        Parameters
        ----------
        layer:
            Logical layer name (``"app"``, ``"host"``, ``"user"", ``"dotenv"``).

        Returns
        -------
        Iterable[str]
            Candidate path strings.

        Side Effects
        ------------
        Emits ``path_candidates`` debug events when paths are discovered.
        """

        paths = self._platform_paths(layer)
        if paths:
            log_debug("path_candidates", layer=layer, path=None, count=len(paths))
        return paths

    def _platform_paths(self, layer: str) -> List[str]:
        """Return discovered paths for *layer* based on the current platform.

        Why
        ----
        Encapsulate platform branching in one place for readability and testing.

        Parameters
        ----------
        layer:
            Logical layer name passed through to platform helpers.

        Returns
        -------
        list[str]
            List of candidate paths (may be empty).
        """

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

        Returns
        -------
        bool
            ``True`` when ``sys.platform`` starts with ``"linux"``.
        """

        return self.platform.startswith("linux")

    @property
    def _is_macos(self) -> bool:
        """Return ``True`` when running on macOS.

        Why
        ----
        Selects macOS-specific directory builders for path resolution.

        Returns
        -------
        bool
            ``True`` when the platform equals ``"darwin"``.
        """

        return self.platform == "darwin"

    @property
    def _is_windows(self) -> bool:
        """Return ``True`` when running on Windows.

        Why
        ----
        Chooses Windows-specific directory builders during resolution.

        Returns
        -------
        bool
            ``True`` when the platform starts with ``"win"``.
        """

        return self.platform.startswith("win")

    def _linux_paths(self, layer: str) -> Iterable[str]:
        """Yield Linux-specific candidates for *layer*.

        Why
        ----
        Mirror the XDG specification and `/etc` conventions documented in the
        system design.

        What
        ----
        Dispatches to helpers that encode Linux directory layouts for the given
        layer and yields their paths.

        Parameters
        ----------
        layer:
            Logical layer identifier passed to the helper lookup.

        Returns
        -------
        Iterable[str]
            Candidate Linux paths (may be empty).
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

        What
        ----
        Dispatches to helpers that encode macOS directory layouts and yields the
        resulting path strings.

        Parameters
        ----------
        layer:
            Logical layer identifier used to pick the helper.

        Returns
        -------
        Iterable[str]
            Candidate macOS paths.
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

        What
        ----
        Dispatches to helpers that encode Windows directory layouts and yields
        the resulting path strings.

        Parameters
        ----------
        layer:
            Logical layer identifier used to pick the helper.

        Returns
        -------
        Iterable[str]
            Candidate Windows paths.
        """

        builders = {
            "app": self._windows_app_paths,
            "host": self._windows_host_paths,
            "user": self._windows_user_paths,
        }
        yield from builders.get(layer, lambda: [])()

    def _linux_app_paths(self) -> Iterable[str]:
        """Yield Linux application-default configuration paths.

        Why
        ----
        Provide deterministic discovery for `/etc/<slug>` layouts.

        Returns
        -------
        Iterable[str]
            Paths under `/etc` (or overridden root) relevant to the app layer.
        """

        etc_root = Path(self.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
        yield from _collect_layer(etc_root / self.slug)

    def _linux_host_paths(self) -> Iterable[str]:
        """Yield Linux host-specific configuration paths.

        Why
        ----
        Allow installations to override defaults per hostname using `/etc/<slug>/hosts`.

        Returns
        -------
        Iterable[str]
            Host-level configuration paths (empty when missing).
        """

        etc_root = Path(self.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
        candidate = etc_root / self.slug / "hosts" / f"{self.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def _linux_user_paths(self) -> Iterable[str]:
        """Yield Linux user-specific configuration paths.

        Why
        ----
        Honour XDG directories while falling back to `~/.config`.

        Returns
        -------
        Iterable[str]
            User-level configuration paths.
        """

        xdg = self.env.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        yield from _collect_layer(base / self.slug)

    def _mac_app_paths(self) -> Iterable[str]:
        """Yield macOS application-default configuration paths.

        Why
        ----
        Follow macOS Application Support directory conventions.

        Returns
        -------
        Iterable[str]
            Application-level configuration paths.
        """

        default_root = Path("/Library/Application Support")
        root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))
        yield from _collect_layer(root / self.vendor / self.application)

    def _mac_host_paths(self) -> Iterable[str]:
        """Yield macOS host-specific configuration paths.

        Why
        ----
        Support host overrides stored under `hosts/<hostname>.toml` within
        Application Support.

        Returns
        -------
        Iterable[str]
            Host-level macOS configuration paths (empty when missing).
        """

        default_root = Path("/Library/Application Support")
        root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))
        candidate = root / self.vendor / self.application / "hosts" / f"{self.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def _mac_user_paths(self) -> Iterable[str]:
        """Yield macOS user-specific configuration paths.

        Why
        ----
        Honour per-user Application Support directories with optional overrides.

        Returns
        -------
        Iterable[str]
            User-level macOS configuration paths.
        """

        home_default = Path.home() / "Library/Application Support"
        home_root = Path(self.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))
        yield from _collect_layer(home_root / self.vendor / self.application)

    def _windows_app_paths(self) -> Iterable[str]:
        """Yield Windows application-default configuration paths.

        Why
        ----
        Mirror `%ProgramData%/<Vendor>/<App>` layouts with override support.

        Returns
        -------
        Iterable[str]
            Application-level Windows configuration paths.
        """

        base = self._program_data_root() / self.vendor / self.application
        yield from _collect_layer(base)

    def _windows_host_paths(self) -> Iterable[str]:
        """Yield Windows host-specific configuration paths.

        Why
        ----
        Enable host overrides within `%ProgramData%/<Vendor>/<App>/hosts`.

        Returns
        -------
        Iterable[str]
            Host-level Windows configuration paths.
        """

        base = self._program_data_root() / self.vendor / self.application
        candidate = base / "hosts" / f"{self.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def _windows_user_paths(self) -> Iterable[str]:
        """Yield Windows user-specific configuration paths.

        Why
        ----
        Honour `%APPDATA%` with a fallback to `%LOCALAPPDATA%` for portable setups.

        Returns
        -------
        Iterable[str]
            User-level Windows configuration paths.
        """

        roaming_base = self._appdata_root() / self.vendor / self.application
        roaming_paths = list(_collect_layer(roaming_base))
        if roaming_paths:
            yield from roaming_paths
            return

        local_base = self._localappdata_root() / self.vendor / self.application
        yield from _collect_layer(local_base)

    def _program_data_root(self) -> Path:
        """Return the base directory for ProgramData lookups.

        Why
        ----
        Centralise overrides for `%ProgramData%` so tests can supply temporary roots.

        Returns
        -------
        Path
            Resolved ProgramData root directory.
        """

        return Path(self.env.get("LIB_LAYERED_CONFIG_PROGRAMDATA", self.env.get("ProgramData", r"C:\ProgramData")))

    def _appdata_root(self) -> Path:
        """Return the user AppData root used for `%APPDATA%` lookups.

        Why
        ----
        Support overrides in tests or portable deployments.

        Returns
        -------
        Path
            Resolved AppData root directory.
        """

        return Path(
            self.env.get("LIB_LAYERED_CONFIG_APPDATA", self.env.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        )

    def _localappdata_root(self) -> Path:
        """Return the fallback LocalAppData root.

        Why
        ----
        Provide a deterministic fallback when `%APPDATA%` does not exist.

        Returns
        -------
        Path
            Resolved LocalAppData root directory.
        """

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

        What
        ----
        Yields paths discovered from the project upward search and appends a
        platform-specific fallback when present.

        Returns
        -------
        Iterable[str]
            Ordered `.env` candidate paths.
        """

        yield from self._project_dotenv_paths()
        extra = self._platform_dotenv_path()
        if extra and extra.is_file():
            yield str(extra)

    def _project_dotenv_paths(self) -> Iterable[str]:
        """Yield `.env` files discovered by walking from the current working directory upward.

        Why
        ----
        Projects often co-locate `.env` files near the repository root; walking
        upward mirrors `dotenv` tooling semantics.

        Returns
        -------
        Iterable[str]
            `.env` paths discovered while traversing parent directories.
        """

        seen: set[Path] = set()
        for directory in [self.cwd, *self.cwd.parents]:
            candidate = directory / ".env"
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.is_file():
                yield str(candidate)

    def _platform_dotenv_path(self) -> Path | None:
        """Return platform-specific `.env` fallback paths.

        Why
        ----
        Provide a deterministic location when the upward search does not find an
        `.env` file.

        Returns
        -------
        Path | None
            Resolved fallback path or ``None`` when unsupported.
        """

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

    What
    ----
    Emits ``config.toml`` when present and lexicographically ordered entries
    from ``config.d`` limited to supported extensions.

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
