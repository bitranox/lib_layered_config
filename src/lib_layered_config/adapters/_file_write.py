"""Write a deployed file so that a failed write never leaves a torn file in its place.

The content goes to a temp file beside the destination, which is then renamed over it: a reader,
and a write that fails half-way (a full disk, a size limit), sees the old file or the whole new one.

A rename gives the destination a new inode, so whatever belonged to the old one is gone: its hard
links, its owner and group, and its extended attributes (on Linux a POSIX ACL and an SELinux label
are attributes). The new file has what a fresh file in that directory gets. When permission setting
is on, the caller sets the layer's mode afterwards, so the rename is wanted. When it is off, the new
file takes the old one's mode, and a destination the rename would change in any other way is
rewritten in place instead, accepting that a failed write there tears it: dropping a file's own ACL,
or giving it the directory's default ACL, changes who may read it, which a torn write never does.

Contents:
    - ``FileFacts``: what a rename would change about a file.
    - ``must_write_in_place``: whether a rename would change the destination.
    - ``write_file``: write *source* to *path* by the rule above.
    - ``write_data``: write bytes held in memory to *path* by the rule above, permission setting off.

Extended attributes are read on Linux only; Python reads none on macOS or Windows, so there only
hard links, owner, group and writability decide. On Windows the replaced file's access list (DACL)
is copied onto the temp file as soon as it is created, before any content goes in
(``_windows_acl.copy_dacl``), so neither the content nor a rename ever gets the directory's.
"""

from __future__ import annotations

import contextlib
import errno
import io
import os
import secrets
import shutil
import stat
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO, Final

from ._windows_acl import copy_dacl

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

__all__ = ["FileFacts", "must_write_in_place", "write_data", "write_file"]

_TEMP_FLAGS: Final = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_NOINHERIT", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
# Owner-only while permission setting is on: the caller tightens the mode after the rename, and a
# secret must never be readable in between. Off, 0o666 lets the umask decide, as a plain create does.
_RESTRICTED_MODE: Final = 0o600
_PLAIN_MODE: Final = 0o666
_TEMP_NAME_TRIES: Final = 100
# Data already in memory is copied in pieces of this size; any size gives the same file.
_DATA_CHUNK_BYTES: Final = 64 * 1024
# A file system that keeps no extended attributes answers these; it has none to lose either.
_NO_XATTR_SUPPORT: Final = frozenset({errno.ENOTSUP, errno.EOPNOTSUPP})


@dataclass(frozen=True)
class FileFacts:
    """What a replace-by-rename would change about a file.

    Attributes:
        links: Hard links to the file (``st_nlink``).
        uid: Owner (``st_uid``; 0 on Windows).
        gid: Group (``st_gid``; 0 on Windows).
        writable: Whether this process may open it for writing.
        xattrs: Extended attributes by name, ``None`` when they could not be read.
    """

    links: int
    uid: int
    gid: int
    writable: bool
    xattrs: Mapping[str, bytes] | None


def must_write_in_place(target: FileFacts, fresh: FileFacts) -> bool:
    """Return whether replacing *target* by a file like *fresh* would change more than its content.

    Args:
        target: The destination as it is.
        fresh: A temp file just created beside it, already given the destination's mode.

    Returns:
        True when the destination has other hard links, another owner or group than a new file
        gets, is not writable by this process, or has extended attributes that differ from the new
        file's by name or value (unreadable ones count as differing).

    Examples:
        >>> same = FileFacts(links=1, uid=1000, gid=1000, writable=True, xattrs={})
        >>> must_write_in_place(same, same)
        False
        >>> must_write_in_place(FileFacts(links=2, uid=1000, gid=1000, writable=True, xattrs={}), same)
        True
    """
    return (
        target.links > 1
        or not target.writable
        or (target.uid, target.gid) != (fresh.uid, fresh.gid)
        or target.xattrs is None
        or fresh.xattrs is None
        or dict(target.xattrs) != dict(fresh.xattrs)
    )


def write_file(path: Path, source: Path, *, restrict: bool, chunk_bytes: int, acl_from: Path | None = None) -> None:
    """Write the content of *source* to *path*, *chunk_bytes* at a time.

    Args:
        path: The destination; its directory exists, and it is a regular file or missing.
        source: The file whose content is written.
        restrict: Permission setting is on: the temp file is owner-only and always renamed into
            place, the caller setting the layer's mode afterwards.
        chunk_bytes: How much of *source* is held at once.
        acl_from: On Windows, the file whose access list the new file gets before it is renamed
            into place; ``None`` takes the replaced file's, and a new file then keeps its
            directory's.

    Raises:
        OSError: Reading *source* or writing *path* failed; *path* is then as it was, except when it
            had to be rewritten in place (see ``must_write_in_place``).
    """
    _write(path, lambda: source.open("rb"), restrict=restrict, chunk_bytes=chunk_bytes, acl_from=acl_from)


def write_data(path: Path, data: bytes) -> None:
    """Write *data* to *path* with permission setting off, by the rule of :func:`write_file`.

    Args:
        path: The destination; its directory exists, and it is a regular file or missing.
        data: The whole content.

    Raises:
        OSError: Writing *path* failed; *path* is then as it was, except when it had to be
            rewritten in place (see ``must_write_in_place``).

    Examples:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     target = Path(tmp) / "example.toml"
        ...     write_data(target, b"key = 1\\n")
        ...     target.read_bytes(), sorted(p.name for p in Path(tmp).iterdir())
        (b'key = 1\\n', ['example.toml'])
    """
    _write(path, lambda: io.BytesIO(data), restrict=False, chunk_bytes=_DATA_CHUNK_BYTES, acl_from=None)


def _write(
    path: Path, open_source: Callable[[], BinaryIO], *, restrict: bool, chunk_bytes: int, acl_from: Path | None
) -> None:
    """Write what *open_source* reads to *path*; see :func:`write_file`."""
    fd, temp = _create_temp(path, mode=_RESTRICTED_MODE if restrict else _PLAIN_MODE)
    try:
        # Written through the descriptor the create opened: taking the destination's mode (0o444,
        # say) must not decide whether the copy can be written; must_write_in_place decides that.
        # The with owns the descriptor from here, so a refusal below still closes it, and on Windows
        # an open handle would block the cleanup delete.
        with os.fdopen(fd, "wb") as handle:
            # Windows gives the new file its directory's ACL; it takes the replaced file's before any
            # content goes in, so the content is never readable by more than the file it replaces.
            copy_dacl(acl_from if acl_from is not None else path, temp)
            in_place = not restrict and _rename_would_change(path, temp)
            if not in_place:
                with open_source() as reader:
                    shutil.copyfileobj(reader, handle, chunk_bytes)
        if in_place:
            _remove_temp(temp)
            _rewrite_in_place(path, open_source, chunk_bytes)
            return
        temp.replace(path)
    except BaseException:
        # A failed cleanup must not replace the error that stopped the write.
        with contextlib.suppress(OSError):
            _remove_temp(temp)
        raise


def _remove_temp(temp: Path) -> None:
    """Delete *temp*, which this process created; a missing one is fine.

    It may hold the destination's mode by now (``_rename_would_change``), and on Windows mode 0o444
    is the read-only attribute, which refuses the delete: the temp then stayed beside the
    destination and its PermissionError, naming the temp, replaced the error that mattered.
    """
    with contextlib.suppress(FileNotFoundError):
        temp.chmod(stat.S_IREAD | stat.S_IWRITE)
    temp.unlink(missing_ok=True)


def _create_temp(path: Path, *, mode: int) -> tuple[int, Path]:
    """Create an empty temp file beside *path* with *mode* (less the umask); its open descriptor and path."""
    for _ in range(_TEMP_NAME_TRIES):
        candidate = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            fd = os.open(candidate, _TEMP_FLAGS, mode)
        except FileExistsError:
            continue
        return fd, candidate
    raise FileExistsError(errno.EEXIST, "no free temporary file name beside the destination", str(path))


def _rename_would_change(path: Path, temp: Path) -> bool:
    """Give *temp* the mode of an existing *path*, then say whether a rename would change *path*."""
    try:
        target = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    # Before reading the temp file's attributes: a chmod rewrites an ACL's mask entry.
    temp.chmod(stat.S_IMODE(target.st_mode))
    return must_write_in_place(_facts(path, target), _facts(temp, temp.stat(follow_symlinks=False)))


def _facts(path: Path, status: os.stat_result) -> FileFacts:
    """The ``FileFacts`` of *path*, whose ``stat`` is *status*."""
    return FileFacts(
        links=status.st_nlink,
        uid=status.st_uid,
        gid=status.st_gid,
        writable=_writable(path),
        xattrs=_xattrs(path),
    )


def _writable(path: Path) -> bool:
    """Whether this process may write *path*, asked by opening it for writing without truncating.

    Not ``os.access``, which answers False on any error and so cannot tell a refusal from a failure.
    """
    try:
        os.close(os.open(path, os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)))
    except PermissionError:
        return False
    return True


def _xattrs(path: Path) -> dict[str, bytes] | None:
    """The extended attributes of *path* by name; ``{}`` off Linux, ``None`` when unreadable."""
    if sys.platform != "linux":
        return {}
    try:
        names = os.listxattr(path, follow_symlinks=False)
        return {name: os.getxattr(path, name, follow_symlinks=False) for name in names}
    except OSError as exc:
        return {} if exc.errno in _NO_XATTR_SUPPORT else None


def _rewrite_in_place(path: Path, open_source: Callable[[], BinaryIO], chunk_bytes: int) -> None:
    """Overwrite *path* through its own inode; the source is opened first, so an unreadable one leaves it."""
    with open_source() as reader, path.open("wb") as writer:
        shutil.copyfileobj(reader, writer, chunk_bytes)
