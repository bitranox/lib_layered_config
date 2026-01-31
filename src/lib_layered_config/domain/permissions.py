"""Permission constants and utilities for deployed configuration files.

This module provides sensible default Unix permissions for deployed configuration
files based on their target layer:

- **App/Host layers**: World-readable, admin-writable (755/644)
  System-wide configuration that needs to be readable by all processes.

- **User layer**: Private to user (700/600)
  Personal configuration that should not be accessible by other users.

On Windows, permissions are skipped since Windows uses ACLs rather than
Unix-style permission bits.
"""

from __future__ import annotations

import os
from pathlib import Path

# App/Host layer defaults (world-readable, admin-writable)
DEFAULT_APP_DIR_MODE: int = 0o755
DEFAULT_APP_FILE_MODE: int = 0o644

# User layer defaults (private to user)
DEFAULT_USER_DIR_MODE: int = 0o700
DEFAULT_USER_FILE_MODE: int = 0o600

# Mapping of layer to default permissions
LAYER_PERMISSIONS: dict[str, dict[str, int]] = {
    "app": {"dir": DEFAULT_APP_DIR_MODE, "file": DEFAULT_APP_FILE_MODE},
    "host": {"dir": DEFAULT_APP_DIR_MODE, "file": DEFAULT_APP_FILE_MODE},
    "user": {"dir": DEFAULT_USER_DIR_MODE, "file": DEFAULT_USER_FILE_MODE},
}


def set_permissions(path: Path, layer: str, *, is_dir: bool = False) -> None:
    """Set appropriate permissions based on layer (POSIX only).

    Args:
        path: Path to set permissions on.
        layer: Target layer ("app", "host", or "user").
        is_dir: True if path is a directory.

    Note:
        No-op on non-POSIX systems (Windows).
    """
    if os.name != "posix":
        return

    perms = LAYER_PERMISSIONS.get(layer, LAYER_PERMISSIONS["app"])
    mode = perms["dir"] if is_dir else perms["file"]
    path.chmod(mode)


def set_custom_permissions(
    path: Path,
    *,
    dir_mode: int | None,
    file_mode: int | None,
    is_dir: bool = False,
) -> None:
    """Set custom permissions (POSIX only).

    Args:
        path: Path to set permissions on.
        dir_mode: Mode for directories (None = skip).
        file_mode: Mode for files (None = skip).
        is_dir: True if path is a directory.

    Note:
        No-op on non-POSIX systems (Windows) or if mode is None.
    """
    if os.name != "posix":
        return

    mode = dir_mode if is_dir else file_mode
    if mode is not None:
        path.chmod(mode)
