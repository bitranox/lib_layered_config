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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..._platform import resolver_platform
from ...domain.errors import ValidationError
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
from ...observability import log_debug, log_warn
from .._path_probe import current_directory
from ._base import HomeDirectoryUnknownError, PlatformContext, PlatformStrategy, deploy_destination
from ._dotenv import DotenvPathFinder
from ._linux import LinuxStrategy
from ._macos import MacOSStrategy
from ._windows import WindowsStrategy

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
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
        env: Mapping[str, str] | None = None,
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
            platform: A ``sys.platform`` value, or one of the aliases ``deploy_config`` takes
                (``macos``, ``mac``, ``windows``, ``win``, ... in any case); stored as the
                ``sys.platform`` identifier it names. Defaults to the current interpreter platform.
            hostname: Hostname used for host-specific configuration lookups. When omitted, the
                machine's ``socket.gethostname()``; a machine hostname that cannot name a file turns
                the host layer off (``host_file_name`` is ``None``) and logs
                ``host_layer_skipped_invalid_hostname`` instead of refusing.
            max_profile_length: Maximum allowed profile name length (default: 64).
                A value above 255, or 0 or negative, uses the absolute maximum of 255 characters.

        Raises:
            ValueError: When vendor, app, slug, profile, or an explicit hostname contain invalid
                path characters.
        """
        self.vendor = validate_vendor_app(vendor, "vendor")
        self.application = validate_vendor_app(app, "app")
        self.slug = validate_identifier(slug, "slug")
        self.profile = validate_profile(profile, max_length=max_profile_length)
        self.cwd = cwd if cwd is not None else current_directory()
        self.env = {**os.environ, **(env or {})}
        self.platform = resolver_platform(platform or sys.platform)
        self._host = _host_file(hostname)
        #: ``<hostname>.toml``, or ``None`` when the machine's hostname cannot name a file.
        self.host_file_name: str | None = None if isinstance(self._host, _HostRefusal) else self._host

        # Build the platform context and select the appropriate strategy
        self._ctx = PlatformContext(
            vendor=self.vendor,
            app=self.application,
            slug=self.slug,
            cwd=self.cwd,
            env=self.env,
            host_file_name=self.host_file_name,
            profile=self.profile,
        )
        self._strategy = self._select_strategy()
        self._dotenv_finder = DotenvPathFinder(self.cwd, self._strategy)

    def require_host_file_name(self) -> str:
        """Return ``<hostname>.toml`` for a write to the host layer.

        Returns:
            The host file name.

        Raises:
            ValidationError: The machine's hostname cannot name a file; the message is the one
                :func:`validate_hostname` gave.
        """
        if isinstance(self._host, _HostRefusal):
            raise ValidationError(self._host.message)
        return self._host

    def destination_for(self, layer: Layer) -> Path:
        """Return the file a deploy writes for *layer*, in the layout the reads of this resolver use.

        Args:
            layer: ``Layer.APP``, ``Layer.HOST`` or ``Layer.USER``.

        Returns:
            ``config.toml`` in the layer's directory, or ``hosts/<hostname>.toml``.

        Raises:
            ValidationError: *layer* is the host layer and the machine's hostname cannot name a file.
            KeyError: *layer* is not one a deploy writes.
            LayerRootNotAbsoluteError, HomeDirectoryUnknownError: The layer's root cannot be used.
        """
        return deploy_destination(self._strategy, layer, host_file_name=self.require_host_file_name)

    @property
    def strategy(self) -> PlatformStrategy:
        """Return the current platform strategy for direct access in tests."""
        return self._strategy

    @property
    def context(self) -> PlatformContext:
        """Return the platform context for direct access in tests."""
        return self._ctx

    def _select_strategy(self) -> PlatformStrategy:
        """Select the platform strategy; a platform with no layout of its own gets the Linux one."""
        family = platform_family(self.platform)
        if family == PlatformFamily.MACOS:
            return MacOSStrategy(self._ctx)
        if family == PlatformFamily.WINDOWS:
            return WindowsStrategy(self._ctx)
        return LinuxStrategy(self._ctx)

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
        return self._record_candidates(Layer.APP, self._strategy.app_paths())

    def host(self) -> Iterable[str]:
        """Return host-specific overrides.

        Allow operators to tailor configuration to individual hosts (e.g.
        ``demo-host.toml``).

        Returns:
            Ordered host-level configuration paths.
        """
        return self._record_candidates(Layer.HOST, self._strategy.host_paths())

    def user(self) -> Iterable[str]:
        """Return user-level configuration locations.

        Capture per-user preferences stored in XDG/macOS/Windows user config
        directories.

        Returns:
            Ordered user-level configuration paths.
        """
        try:
            return self._record_candidates(Layer.USER, self._strategy.user_paths())
        except HomeDirectoryUnknownError:
            # A uid with no home has no user configuration to read; the other layers still load
            # (the rule R1-F2 applies to an unusable machine hostname and the host layer).
            log_warn("user_layer_skipped_no_home", layer=Layer.USER.value, path=None)
            return []

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
        """Materialise *candidates* for *layer* and log how many were found."""
        paths = list(candidates)
        if paths:
            log_debug("path_candidates", layer=layer.value, path=None, count=len(paths))
        return paths


@dataclass(frozen=True, slots=True)
class _HostRefusal:
    """Why the machine's hostname names no host file: the message :func:`validate_hostname` gave."""

    message: str


def _host_file(explicit: str | None) -> str | _HostRefusal:
    """Return ``<hostname>.toml``, or the refusal for a machine hostname that cannot name a file.

    An explicit *hostname* is the caller's own input and is refused as before. The machine's name
    is not: no caller can change it, so a name the rules refuse (non-ASCII, a Windows reserved
    name) turns off only the host layer, which can hold no file under that name anyway, instead
    of every read and deploy (user decision 2026-11-16, R1-F2).

    Args:
        explicit: The hostname a caller passed, or ``None`` (or empty) for the machine's.

    Returns:
        The host file name, or the refusal of the machine's hostname.

    Raises:
        ValidationError: *explicit* is refused.
    """
    if explicit:
        return f"{validate_hostname(explicit)}.toml"
    machine = socket.gethostname()
    try:
        return f"{validate_hostname(machine)}.toml"
    except ValidationError as exc:
        log_warn("host_layer_skipped_invalid_hostname", hostname=machine, reason=str(exc))
        return _HostRefusal(str(exc))
