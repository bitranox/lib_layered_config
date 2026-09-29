"""Permission constants and utilities for deployed configuration files.

This module provides sensible default Unix permissions for deployed configuration
files based on their target layer:

- **App/Host layers**: World-readable, admin-writable (755/644)
  System-wide configuration that needs to be readable by all processes.

- **User layer**: Private to user (700/600)
  Personal configuration that should not be accessible by other users.

On Windows, modes are skipped since Windows uses ACLs rather than Unix-style
permission bits; a refused mode is refused on every platform.
"""

from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING

from .deploy_mode import DeployMode, ModeKind
from .identifiers import Layer

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "DEFAULT_APP_DIR_MODE",
    "DEFAULT_APP_FILE_MODE",
    "DEFAULT_USER_DIR_MODE",
    "DEFAULT_USER_FILE_MODE",
    "LAYER_PERMISSIONS",
    "apply_mode",
    "modes_apply",
    "set_custom_permissions",
    "set_permissions",
]

# App/Host layer defaults (world-readable, admin-writable)
DEFAULT_APP_DIR_MODE: int = 0o755
DEFAULT_APP_FILE_MODE: int = 0o644

# User layer defaults (private to user)
DEFAULT_USER_DIR_MODE: int = 0o700
DEFAULT_USER_FILE_MODE: int = 0o600

# Mapping of layer to default permissions (keyed by the Layer enum values)
LAYER_PERMISSIONS: dict[str, dict[str, int]] = {
    Layer.APP.value: {"dir": DEFAULT_APP_DIR_MODE, "file": DEFAULT_APP_FILE_MODE},
    Layer.HOST.value: {"dir": DEFAULT_APP_DIR_MODE, "file": DEFAULT_APP_FILE_MODE},
    Layer.USER.value: {"dir": DEFAULT_USER_DIR_MODE, "file": DEFAULT_USER_FILE_MODE},
}


def modes_apply() -> bool:
    """Return whether this platform applies Unix permission modes (POSIX); Windows uses ACLs."""
    return os.name == "posix"


def apply_mode(path: Path, mode: DeployMode) -> None:
    """Set *mode* on *path* where the platform applies modes; a no-op on Windows.

    Taking a :class:`DeployMode` rather than an int is the guard: an unsafe mode cannot be
    constructed, so it cannot reach ``chmod``.
    """
    if modes_apply():
        path.chmod(mode.value)


def _deprecation(name: str) -> str:
    """Return the deprecation message for the setter *name*, naming its replacement."""
    return (
        f"{name} is deprecated and will be removed in a future major version; "
        "use apply_mode(path, DeployMode(mode, kind))"
    )


def set_permissions(path: Path, layer: str, *, is_dir: bool = False) -> None:
    """Set the built-in mode for *layer* (POSIX only).

    Deprecated: nothing in the library calls it since ``deploy_config`` decides modes from
    :class:`~lib_layered_config.domain.deploy_permissions.DeployPermissions`. Use
    ``apply_mode(path, DeployMode(mode, kind))`` instead.

    Args:
        path: Path to set permissions on.
        layer: Target layer ("app", "host", or "user"); an unknown layer uses the app layer's.
        is_dir: True if path is a directory.
    """
    warnings.warn(_deprecation("set_permissions"), DeprecationWarning, stacklevel=2)
    perms = LAYER_PERMISSIONS.get(layer, LAYER_PERMISSIONS[Layer.APP.value])
    kind = ModeKind.DIRECTORY if is_dir else ModeKind.FILE
    apply_mode(path, DeployMode(perms["dir"] if is_dir else perms["file"], kind))


def set_custom_permissions(
    path: Path,
    *,
    dir_mode: int | None,
    file_mode: int | None,
    is_dir: bool = False,
) -> None:
    """Set a caller-chosen mode (POSIX only); ``None`` skips.

    Deprecated: nothing in the library calls it. Use ``apply_mode(path, DeployMode(mode, kind))``
    instead, which refuses an unsafe mode the same way.

    Args:
        path: Path to set permissions on.
        dir_mode: Mode for directories (None = skip).
        file_mode: Mode for files (None = skip).
        is_dir: True if path is a directory.

    Raises:
        DeployModeError: The chosen mode is out of range or unsafe. Checked on every platform,
            before any ``chmod``.
    """
    warnings.warn(_deprecation("set_custom_permissions"), DeprecationWarning, stacklevel=2)
    mode = dir_mode if is_dir else file_mode
    if mode is None:
        return
    apply_mode(path, DeployMode(mode, ModeKind.DIRECTORY if is_dir else ModeKind.FILE))
