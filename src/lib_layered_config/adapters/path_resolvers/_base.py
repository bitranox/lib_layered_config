"""Base classes and shared utilities for platform-specific path resolution.

Define the contract for platform strategies and provide shared utilities
used across all platform implementations.

All path handling uses ``pathlib.Path`` for cross-platform compatibility.
UNC network paths (e.g., ``//server/share``) are supported on Windows via
environment variable overrides and handled natively by ``pathlib``.

Contents:
    - ``PlatformContext``: dataclass holding resolution context (vendor, app, etc.)
    - ``PlatformStrategy``: abstract base for platform-specific resolvers
    - ``_collect_layer``: shared helper for enumerating config files
    - ``_ALLOWED_EXTENSIONS``: supported config file extensions
"""

from __future__ import annotations

import abc
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: Supported structured configuration file extensions used when expanding
#: ``config.d`` directories.
_ALLOWED_EXTENSIONS = (".toml", ".yaml", ".yml", ".json")
"""File suffixes considered when expanding ``config.d`` directories.

Ensure platform-specific discovery yields consistent formats and avoids
non-structured files.

Tuple of lowercase extensions in precedence order.
"""


@dataclass(frozen=True)
class PlatformContext:
    """Immutable context required for path resolution.

    Encapsulate all inputs needed by platform strategies to resolve paths,
    enabling dependency injection and simplified testing.

    Attributes:
        vendor: Vendor name used in platform-specific directory structures.
        app: Application name used in platform-specific directory structures.
        slug: Short identifier used in Linux/XDG paths.
        cwd: Current working directory for project-relative searches.
        env: Environment variable mapping (for overrides and XDG lookups).
        hostname: Hostname for host-specific configuration lookups.
        profile: Optional profile name for environment-specific configurations.
    """

    vendor: str
    app: str
    slug: str
    cwd: Path
    env: dict[str, str]
    hostname: str
    profile: str | None = None


class PlatformStrategy(abc.ABC):
    """Abstract base class for platform-specific path resolution strategies.

    Encapsulate platform-specific logic in dedicated classes, keeping each
    implementation small and testable.

    Subclasses:
        - ``LinuxStrategy``: XDG and ``/etc`` based resolution
        - ``MacOSStrategy``: Application Support based resolution
        - ``WindowsStrategy``: ProgramData/AppData based resolution
    """

    def __init__(self, ctx: PlatformContext) -> None:
        """Store the resolution context.

        Args:
            ctx: Immutable context containing vendor, app, slug, env, etc.
        """
        self.ctx = ctx

    def _profile_segment(self) -> Path:
        """Return the profile path segment or an empty path.

        When a profile is configured, all paths should include a
        ``profile/<name>/`` subdirectory. This helper centralises that logic.

        Returns:
            ``Path("profile/<name>")`` when profile is set, otherwise ``Path()``.
        """
        if self.ctx.profile:
            return Path("profile") / self.ctx.profile
        return Path()

    @abc.abstractmethod
    def app_paths(self) -> Iterable[str]:
        """Yield application-default configuration paths.

        Returns:
            Paths for the app layer (lowest precedence system-wide defaults).
        """

    @abc.abstractmethod
    def host_paths(self) -> Iterable[str]:
        """Yield host-specific configuration paths.

        Returns:
            Paths for the host layer (machine-specific overrides).
        """

    @abc.abstractmethod
    def user_paths(self) -> Iterable[str]:
        """Yield user-specific configuration paths.

        Returns:
            Paths for the user layer (per-user preferences).
        """

    @abc.abstractmethod
    def dotenv_path(self) -> Path | None:
        """Return the platform-specific ``.env`` fallback path.

        Returns:
            Fallback ``.env`` location or ``None`` if unsupported.
        """


def collect_layer(base: Path) -> Iterable[str]:
    """Yield canonical config file path under *base* for file-level expansion.

    Normalise discovery across operating systems while respecting preferred
    configuration formats.

    Yields ``config.toml`` when present or when its companion ``config.d``
    directory exists. The actual .d directory expansion is handled by
    ``_layers._load_entry_with_dot_d``.

    Args:
        base: Base directory for a particular layer.

    Returns:
        Absolute file paths discovered under ``base``.

    Examples:
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
        >>> sorted(Path(p).name for p in collect_layer(root))
        ['config.toml']
        >>> tmp.cleanup()
    """
    config_file = base / "config.toml"
    config_d_dir = base / "config.d"

    if config_file.is_file() or config_d_dir.is_dir():
        yield str(config_file)
