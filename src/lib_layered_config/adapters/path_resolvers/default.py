"""Filesystem path resolution using platform-specific strategies.

Implement the :class:`lib_layered_config.application.ports.PathResolver`
port using the Strategy pattern for clean platform-specific handling.

Contents:
    - ``DefaultPathResolver``: public adapter consumed by the composition root.
    - Platform strategies in ``_linux.py``, ``_macos.py``, ``_windows.py``.

System Integration:
    Produces ordered path lists for the core merge pipeline. All filesystem
    knowledge stays here so inner layers remain filesystem-agnostic.
"""

from __future__ import annotations

import os
import socket
import sys
from typing import TYPE_CHECKING

from ...domain.identifiers import (
    DEFAULT_MAX_PROFILE_LENGTH,
    Layer,
    PlatformFamily,
    platform_family,
    validate_hostname,
    validate_identifier,
    validate_profile,
    validate_vendor_app,
)
from ...observability import log_debug
from .._path_probe import current_directory
from ._base import PlatformContext, PlatformStrategy
from ._dotenv import DotenvPathFinder
from ._linux import LinuxStrategy
from ._macos import MacOSStrategy
from ._windows import WindowsStrategy

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


__all__ = [
    "DefaultPathResolver",
]


class DefaultPathResolver:
    """Resolve candidate paths for each configuration layer.

    Centralise path discovery so the composition root stays platform-agnostic
    and easy to test.

    Architecture:
        Uses the Strategy pattern to delegate platform-specific logic to dedicated
        classes (``LinuxStrategy``, ``MacOSStrategy``, ``WindowsStrategy``),
        keeping the main resolver focused on orchestration.
    """

    def __init__(
        self,
        *,
        vendor: str,
        app: str,
        slug: str,
        profile: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        platform: str | None = None,
        hostname: str | None = None,
        max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
    ) -> None:
        """Store context required to resolve filesystem locations.

        Args:
            vendor / app / slug: Naming context injected into platform-specific directory structures.
            profile: Optional profile name for environment-specific configurations
                (e.g., "test", "production"). When set, paths include a
                ``profile/<name>/`` subdirectory.
            cwd: Working directory to use when searching for ``.env`` files.
            env: Optional environment mapping that overrides ``os.environ`` values
                (useful for deterministic tests).
            platform: Platform identifier (``sys.platform`` clone). Defaults to the
                current interpreter platform.
            hostname: Hostname used for host-specific configuration lookups.
            max_profile_length: Maximum allowed profile name length (default: 64).
                Set to 0 or negative to disable length checking.

        Raises:
            ValueError: When vendor, app, slug, profile, or hostname contain invalid path characters.
        """
        self.vendor = validate_vendor_app(vendor, "vendor")
        self.application = validate_vendor_app(app, "app")
        self.slug = validate_identifier(slug, "slug")
        self.profile = validate_profile(profile, max_length=max_profile_length)
        self.cwd = cwd if cwd is not None else current_directory()
        self.env = {**os.environ, **(env or {})}
        self.platform = platform or sys.platform
        self.hostname = validate_hostname(hostname or socket.gethostname())

        # Build the platform context and select the appropriate strategy
        self._ctx = PlatformContext(
            vendor=self.vendor,
            app=self.application,
            slug=self.slug,
            cwd=self.cwd,
            env=self.env,
            hostname=self.hostname,
            profile=self.profile,
        )
        self._strategy = self._select_strategy()
        self._dotenv_finder = DotenvPathFinder(self.cwd, self._strategy)

    @property
    def strategy(self) -> PlatformStrategy | None:
        """Return the current platform strategy for direct access in tests."""
        return self._strategy

    @property
    def context(self) -> PlatformContext:
        """Return the platform context for direct access in tests."""
        return self._ctx

    def _select_strategy(self) -> PlatformStrategy | None:
        """Select the platform strategy, or ``None`` for a platform with no known layout."""
        family = platform_family(self.platform)
        if family == PlatformFamily.LINUX:
            return LinuxStrategy(self._ctx)
        if family == PlatformFamily.MACOS:
            return MacOSStrategy(self._ctx)
        if family == PlatformFamily.WINDOWS:
            return WindowsStrategy(self._ctx)
        return None

    def app(self) -> Iterable[str]:
        """Return candidate system-wide configuration paths.

        Provide the lowest-precedence defaults shared across machines.

        Returns:
            Ordered path strings for the application defaults layer.

        Examples:
            >>> import os
            >>> from pathlib import Path
            >>> from tempfile import TemporaryDirectory
            >>> tmp = TemporaryDirectory()
            >>> root = Path(tmp.name)
            >>> (root / 'demo').mkdir(parents=True, exist_ok=True)
            >>> body = os.linesep.join(['[settings]', 'value=1'])
            >>> _ = (root / 'demo' / 'config.toml').write_text(body, encoding='utf-8')
            >>> resolver = DefaultPathResolver(
            ...     vendor='Acme', app='Demo', slug='demo', env={'LIB_LAYERED_CONFIG_ETC': str(root)}, platform='linux'
            ... )
            >>> [Path(p).name for p in resolver.app()]
            ['config.toml']
            >>> tmp.cleanup()
        """
        strategy = self._strategy
        return self._record_candidates(Layer.APP, strategy.app_paths() if strategy is not None else ())

    def host(self) -> Iterable[str]:
        """Return host-specific overrides.

        Allow operators to tailor configuration to individual hosts (e.g.
        ``demo-host.toml``).

        Returns:
            Ordered host-level configuration paths.
        """
        strategy = self._strategy
        return self._record_candidates(Layer.HOST, strategy.host_paths() if strategy is not None else ())

    def user(self) -> Iterable[str]:
        """Return user-level configuration locations.

        Capture per-user preferences stored in XDG/macOS/Windows user config
        directories.

        Returns:
            Ordered user-level configuration paths.
        """
        strategy = self._strategy
        return self._record_candidates(Layer.USER, strategy.user_paths() if strategy is not None else ())

    def dotenv(self) -> Iterable[str]:
        """Return candidate ``.env`` locations discovered during path resolution.

        `.env` files often live near the project root; this helper provides the
        ordered search list for the dotenv adapter.

        Returns:
            Ordered `.env` path strings.
        """
        return list(self._dotenv_finder.find_paths())

    @staticmethod
    def _record_candidates(layer: Layer, candidates: Iterable[str]) -> list[str]:
        """Materialise *candidates* for *layer* and log how many were found.

        An unknown platform has no strategy, so its callers pass an empty iterable and nothing is logged.
        """
        paths = list(candidates)
        if paths:
            log_debug("path_candidates", layer=layer.value, path=None, count=len(paths))
        return paths
