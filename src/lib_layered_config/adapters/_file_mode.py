"""Set a deployed file's Unix mode, where the platform has modes.

The modes themselves and their safety rules are domain values (``domain.deploy_mode.DeployMode``,
``domain.permissions``); the chmod and the platform check are filesystem and platform I/O, so they
live here, beside the write that comes before them (``_file_write``).

Contents:
    - ``modes_apply``: whether this platform applies Unix permission modes.
    - ``apply_mode``: set a ``DeployMode`` on a path, a no-op where modes do not apply.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from ..domain.deploy_mode import DeployMode

__all__ = ["apply_mode", "modes_apply"]


def modes_apply() -> bool:
    """Return whether this platform applies Unix permission modes (POSIX); Windows uses ACLs.

    Examples:
        >>> modes_apply() is (os.name == "posix")
        True
    """
    return os.name == "posix"


def apply_mode(path: Path, mode: DeployMode) -> None:
    """Set *mode* on *path* where the platform applies modes; a no-op on Windows.

    Taking a :class:`DeployMode` rather than an int is the guard: an unsafe mode cannot be
    constructed, so it cannot reach ``chmod``.

    Args:
        path: The file or directory to change.
        mode: The mode to set.
    """
    if modes_apply():
        path.chmod(mode.value)
