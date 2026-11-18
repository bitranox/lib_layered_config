"""Permission constants and utilities for deployed configuration files.

This module provides sensible default Unix permissions for deployed configuration
files based on their target layer:

- **App/Host layers**: World-readable, admin-writable (755/644)
  System-wide configuration that needs to be readable by all processes.

- **User layer**: Private to user (700/600)
  Personal configuration that should not be accessible by other users.

Setting a mode on a file (``apply_mode``) is filesystem I/O and lives in
``adapters._file_mode``; on Windows it is skipped, since Windows uses ACLs. A refused mode
(``DeployMode``) is refused on every platform.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple

from .identifiers import Layer

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "DEFAULT_APP_DIR_MODE",
    "DEFAULT_APP_FILE_MODE",
    "DEFAULT_USER_DIR_MODE",
    "DEFAULT_USER_FILE_MODE",
    "LAYER_PERMISSIONS",
    "DefaultLayerModes",
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
