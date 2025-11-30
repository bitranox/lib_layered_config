"""Base classes and shared utilities for platform-specific path resolution.

Purpose
    Define the contract for platform strategies and provide shared utilities
    used across all platform implementations.

Contents
    - ``PlatformContext``: dataclass holding resolution context (vendor, app, etc.)
    - ``PlatformStrategy``: abstract base for platform-specific resolvers
    - ``_collect_layer``: shared helper for enumerating config files
    - ``_ALLOWED_EXTENSIONS``: supported config file extensions
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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


@dataclass(frozen=True)
class PlatformContext:
    """Immutable context required for path resolution.

    Why
    ----
    Encapsulate all inputs needed by platform strategies to resolve paths,
    enabling dependency injection and simplified testing.

    Attributes
    ----------
    vendor:
        Vendor name used in platform-specific directory structures.
    app:
        Application name used in platform-specific directory structures.
    slug:
        Short identifier used in Linux/XDG paths.
    cwd:
        Current working directory for project-relative searches.
    env:
        Environment variable mapping (for overrides and XDG lookups).
    hostname:
        Hostname for host-specific configuration lookups.
    """

    vendor: str
    app: str
    slug: str
    cwd: Path
    env: dict[str, str]
    hostname: str


class PlatformStrategy(abc.ABC):
    """Abstract base class for platform-specific path resolution strategies.

    Why
    ----
    Encapsulate platform-specific logic in dedicated classes, keeping each
    implementation small and testable.

    Subclasses
    ----------
    - ``LinuxStrategy``: XDG and ``/etc`` based resolution
    - ``MacOSStrategy``: Application Support based resolution
    - ``WindowsStrategy``: ProgramData/AppData based resolution
    """

    def __init__(self, ctx: PlatformContext) -> None:
        """Store the resolution context.

        Parameters
        ----------
        ctx:
            Immutable context containing vendor, app, slug, env, etc.
        """
        self.ctx = ctx

    @abc.abstractmethod
    def app_paths(self) -> Iterable[str]:
        """Yield application-default configuration paths.

        Returns
        -------
        Iterable[str]
            Paths for the app layer (lowest precedence system-wide defaults).
        """

    @abc.abstractmethod
    def host_paths(self) -> Iterable[str]:
        """Yield host-specific configuration paths.

        Returns
        -------
        Iterable[str]
            Paths for the host layer (machine-specific overrides).
        """

    @abc.abstractmethod
    def user_paths(self) -> Iterable[str]:
        """Yield user-specific configuration paths.

        Returns
        -------
        Iterable[str]
            Paths for the user layer (per-user preferences).
        """

    @abc.abstractmethod
    def dotenv_path(self) -> Path | None:
        """Return the platform-specific ``.env`` fallback path.

        Returns
        -------
        Path | None
            Fallback ``.env`` location or ``None`` if unsupported.
        """


def collect_layer(base: Path) -> Iterable[str]:
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
    >>> sorted(Path(p).name for p in collect_layer(root))
    ['10-extra.json', 'config.toml']
    >>> tmp.cleanup()
    """
    config_file = base / "config.toml"
    if config_file.is_file():
        yield str(config_file)
    yield from _collect_config_d(base / "config.d")


def _collect_config_d(config_dir: Path) -> Iterable[str]:
    """Yield config files from a config.d directory."""
    if not config_dir.is_dir():
        return
    for path in sorted(config_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in _ALLOWED_EXTENSIONS:
            yield str(path)
