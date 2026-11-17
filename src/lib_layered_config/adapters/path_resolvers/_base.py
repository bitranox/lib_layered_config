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
    - ``override_root``: a ``LIB_LAYERED_CONFIG_*`` root override, refused when it is not rooted
    - ``_ALLOWED_EXTENSIONS``: supported config file extensions
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.errors import HomeDirectoryUnknownError, LayerRootNotAbsoluteError
from ...domain.printable import escape_controls
from .._path_probe import PathKind, checked_kind

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

__all__ = [
    "HomeDirectoryUnknownError",
    "PlatformContext",
    "PlatformStrategy",
    "collect_layer",
    "config_path_present",
    "home_directory",
    "override_root",
]


def home_directory() -> Path:
    """Return the current user's home directory.

    Raises:
        HomeDirectoryUnknownError: ``Path.home()`` cannot answer: HOME unset and the uid has no
            passwd entry, or on Windows USERPROFILE, HOMEDRIVE and HOMEPATH all unset.
    """
    try:
        return Path.home()
    except RuntimeError as exc:
        # Path.home() reads USERPROFILE on Windows and ignores HOME there, so name what it reads.
        home_variable = "USERPROFILE" if os.name == "nt" else "HOME"
        raise HomeDirectoryUnknownError(
            f"cannot determine the home directory for the user layer: set {home_variable}, or the variable "
            "naming the user-layer root (XDG_CONFIG_HOME, LIB_LAYERED_CONFIG_MAC_HOME_ROOT, "
            "LIB_LAYERED_CONFIG_APPDATA)"
        ) from exc


def override_root(env: Mapping[str, str], name: str, default: Callable[[], Path]) -> Path:
    """The root the override *name* names, or *default()* when *name* is not set.

    *default* is called only when it is needed, so a host that cannot answer ``Path.home()`` still
    resolves a root the environment names.

    Raises:
        LayerRootNotAbsoluteError: The value has no root (empty, ``rel/etc``, or a Windows
            drive-relative ``C:x``), so every layer path - and every deploy - would land under the
            current working directory. A rooted path is enough: ``/etc`` names the same place
            whichever OS the resolver runs on, while ``is_absolute()`` is false for it on Windows.

    Examples:
        >>> env = {"LIB_LAYERED_CONFIG_ETC": "/opt/etc"}
        >>> override_root(env, "LIB_LAYERED_CONFIG_ETC", lambda: Path("/etc")).as_posix()
        '/opt/etc'
        >>> override_root({}, "LIB_LAYERED_CONFIG_ETC", lambda: Path("/etc")).as_posix()
        '/etc'
    """
    if name not in env:
        return default()
    value = env[name]
    if not Path(value).root:
        raise LayerRootNotAbsoluteError(
            f"The {name} root '{escape_controls(value)}' is not an absolute path; set {name} to an absolute path "
            "or unset it"
        )
    return Path(value)


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
        cwd: Current working directory for project-relative searches; ``None`` when the OS
            cannot name it.
        env: Environment variable mapping (for overrides and XDG lookups).
        host_file_name: ``<hostname>.toml`` for host-specific configuration lookups, or ``None``
            when the machine's hostname cannot name a file, which turns the host layer off.
        profile: Optional profile name for environment-specific configurations.
    """

    vendor: str
    app: str
    slug: str
    cwd: Path | None
    env: dict[str, str]
    host_file_name: str | None
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


def config_path_present(path: Path) -> bool:
    """Return whether a discovered config file path goes to the loader.

    A file loads. A directory goes too, so the loader refuses it naming the path: filtered out
    here, a directory where a layer's config file belongs was skipped in silence and the
    configuration fell back to the layers below, although a directory at ``default_file`` already
    refused. Anything else (missing, a FIFO or socket the loader must not open) is not a config
    file and is passed over.

    Args:
        path: A layer's config file path, as the platform resolver discovered it.

    Returns:
        ``True`` for a file or a directory.

    Raises:
        InvalidFormatError: *path* cannot be checked (``read_config`` raises it as
            ``LayerLoadError``).

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> tmp = TemporaryDirectory()
        >>> root = Path(tmp.name)
        >>> (root / 'config.toml').mkdir()
        >>> config_path_present(root / 'config.toml'), config_path_present(root / 'absent.toml')
        (True, False)
        >>> tmp.cleanup()
    """
    return checked_kind(path) in (PathKind.FILE, PathKind.DIRECTORY)


def collect_layer(base: Path) -> Iterable[str]:
    """Yield canonical config file path under *base* for file-level expansion.

    Normalise discovery across operating systems while respecting preferred
    configuration formats.

    Yields ``config.toml`` when present (`config_path_present`) or when its
    companion ``config.d`` directory exists. The actual .d directory expansion is handled by
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

    if config_path_present(config_file) or checked_kind(config_d_dir) is PathKind.DIRECTORY:
        yield str(config_file)
