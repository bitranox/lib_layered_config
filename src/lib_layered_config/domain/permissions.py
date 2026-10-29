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
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple

from .identifiers import Layer

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from .deploy_mode import DeployMode

__all__ = [
    "DEFAULT_APP_DIR_MODE",
    "DEFAULT_APP_FILE_MODE",
    "DEFAULT_USER_DIR_MODE",
    "DEFAULT_USER_FILE_MODE",
    "LAYER_PERMISSIONS",
    "DefaultLayerModes",
    "apply_mode",
    "modes_apply",
]

# App/Host layer defaults (world-readable, admin-writable)
DEFAULT_APP_DIR_MODE: int = 0o755
DEFAULT_APP_FILE_MODE: int = 0o644

# User layer defaults (private to user)
DEFAULT_USER_DIR_MODE: int = 0o700
DEFAULT_USER_FILE_MODE: int = 0o600


class DefaultLayerModes(NamedTuple):
    """The built-in directory and file mode of one deployment layer, as plain ints."""

    directory: int
    file: int


#: The built-in modes of every deployment layer. Read-only, so a caller cannot change the
#: defaults every later deploy falls back to. Keyed by ``Layer`` members; since ``Layer`` is a
#: ``(str, Enum)``, a lookup by the plain value (``"app"``) finds the same entry.
LAYER_PERMISSIONS: Final[Mapping[Layer, DefaultLayerModes]] = MappingProxyType(
    {
        Layer.APP: DefaultLayerModes(directory=DEFAULT_APP_DIR_MODE, file=DEFAULT_APP_FILE_MODE),
        Layer.HOST: DefaultLayerModes(directory=DEFAULT_APP_DIR_MODE, file=DEFAULT_APP_FILE_MODE),
        Layer.USER: DefaultLayerModes(directory=DEFAULT_USER_DIR_MODE, file=DEFAULT_USER_FILE_MODE),
    }
)


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
