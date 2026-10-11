"""Classify a filesystem path the same way on every supported Python.

Before Python 3.14, ``Path.is_file()``, ``is_dir()`` and ``exists()`` raise ``PermissionError``
when a directory on the path cannot be entered; from 3.14 they return ``False``. Left to them, one
configuration crashed on one interpreter and was silently dropped on another. This module calls
``Path.stat()`` (unchanged in 3.14) and reads the error itself, so the answer does not depend on the interpreter.

Contents:
    - ``PathKind``: what a probe found.
    - ``PathProbe``: the kind plus the error when the path could not be checked (an ``OSError``, or
      the ``ValueError`` a NUL byte or an unencodable name raises).
    - ``probe_path``: never raises; a search uses it and skips what it cannot check.
    - ``checked_kind``: refuses a path it cannot check; a layer location or a named file uses it.
    - ``config_path_unreadable``: the refusal, shared with the file readers.
    - ``current_directory``: the working directory, or ``None`` when the OS cannot name it.
"""

from __future__ import annotations

import errno
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from ..domain.errors import InvalidFormatError
from ..observability import log_debug, log_error

__all__ = ["PathKind", "PathProbe", "checked_kind", "config_path_unreadable", "current_directory", "probe_path"]

# What pathlib before 3.14 already read as "not there": a missing entry, a file where a directory
# was expected, a closed descriptor, a symlink loop, and Windows' invalid-name / drive-not-ready /
# unresolvable-name codes. Keeping exactly that set leaves those answers unchanged on every version.
_ABSENT_ERRNOS: Final = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP})
_ABSENT_WINERRORS: Final = frozenset({21, 123, 1921})


class PathKind(Enum):
    """What :func:`probe_path` found at a path."""

    MISSING = "missing"
    FILE = "file"
    DIRECTORY = "directory"
    OTHER = "other"
    CANNOT_CHECK = "cannot_check"


@dataclass(frozen=True)
class PathProbe:
    """The kind of a path, and the error when it could not be checked.

    Attributes:
        kind: What the probe found.
        error: The ``stat`` error when *kind* is ``CANNOT_CHECK``; otherwise ``None``.
    """

    kind: PathKind
    error: OSError | ValueError | None = None


def probe_path(path: Path) -> PathProbe:
    """Return what is at *path* without raising.

    A permission wall, or any other error that does not mean "absent", is ``CANNOT_CHECK`` with
    the error attached, so a search can skip it and a layer can refuse it.

    Args:
        path: The path to classify.

    Returns:
        The classification.

    Examples:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     probe_path(Path(tmp)).kind, probe_path(Path(tmp) / "absent").kind
        (<PathKind.DIRECTORY: 'directory'>, <PathKind.MISSING: 'missing'>)
    """
    try:
        mode = path.stat().st_mode
    except OSError as error:
        if _means_absent(error):
            return PathProbe(PathKind.MISSING)
        return PathProbe(PathKind.CANNOT_CHECK, error)
    except ValueError as error:
        # A NUL byte or an unencodable name: no file can have it, and pathlib answered False for it
        # on every Python, so it is a path that cannot be checked rather than a crash.
        return PathProbe(PathKind.CANNOT_CHECK, error)
    if stat.S_ISREG(mode):
        return PathProbe(PathKind.FILE)
    if stat.S_ISDIR(mode):
        return PathProbe(PathKind.DIRECTORY)
    return PathProbe(PathKind.OTHER)


def checked_kind(path: Path) -> PathKind:
    """Return what is at *path*, refusing a path that cannot be checked.

    Args:
        path: A layer's own location or a file the caller named.

    Returns:
        The kind; never ``CANNOT_CHECK``.

    Raises:
        InvalidFormatError: *path* cannot be checked (``read_config`` raises it as
            ``LayerLoadError``).

    Examples:
        >>> from pathlib import Path
        >>> checked_kind(Path("/nonexistent-lib-layered-config-probe/config.toml"))
        <PathKind.MISSING: 'missing'>
    """
    probe = probe_path(path)
    if probe.error is not None:
        raise config_path_unreadable(path, probe.error)
    return probe.kind


def config_path_unreadable(path: Path, error: OSError | ValueError) -> InvalidFormatError:
    """Log and build the refusal for a configuration path that cannot be checked or read.

    Without it the layer would crash with a bare ``OSError`` on one Python and fall back to lower
    layers without a trace on another.

    Args:
        path: The configuration path.
        error: The error behind it.

    Returns:
        The error to raise.

    Examples:
        >>> from pathlib import Path
        >>> str(config_path_unreadable(Path("config.toml"), PermissionError(13, "Permission denied")))
        'config.toml cannot be read: Permission denied'
    """
    reason = error.strerror if isinstance(error, OSError) and error.strerror else str(error)
    message = f"{path} cannot be read: {reason}"
    log_error("config_path_unreadable", path=str(path), error=message)
    return InvalidFormatError(message)


def current_directory() -> Path | None:
    """Return the working directory, or ``None`` when the operating system cannot name it.

    ``Path.cwd()`` (``os.getcwd()``) fails on macOS in a directory the user cannot enter, and on any POSIX system in
    one that was removed. The ``.env`` search starts there, so it has nowhere to start and finds
    nothing - the same answer as for a directory it cannot enter.

    Returns:
        The working directory, or ``None``.

    Examples:
        >>> current_directory() == Path.cwd()
        True
    """
    try:
        return Path.cwd()
    except OSError as error:
        log_debug("working_directory_unknown", error=str(error))
        return None


def _means_absent(error: OSError) -> bool:
    """Return whether *error* says the path is not there, as pathlib before 3.14 read it."""
    return error.errno in _ABSENT_ERRNOS or getattr(error, "winerror", None) in _ABSENT_WINERRORS
