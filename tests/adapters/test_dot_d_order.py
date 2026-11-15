"""``.d`` files are ordered by their names' exact characters, the same on every OS.

Windows paths compare case-insensitively and POSIX paths do not, so sorting ``Path`` objects put
``Z.toml`` after ``a-extra.toml`` on Windows and before it everywhere else: one configuration
directory merged with a different winner per host. Pure paths of both flavours run on any OS, so
the Windows order is pinned here without a Windows host.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

from lib_layered_config.adapters.file_loaders._dot_d import in_dot_d_order
from tests.support.os_markers import os_agnostic

_NAMES = ["b-local.toml", "A-base.toml", "10-db.toml", "a-extra.toml", "Z.toml", "\u00e9t\u00e9.toml"]
# Code-point order: digits, then upper case, then lower case, then non-ASCII.
_EXPECTED = ["10-db.toml", "A-base.toml", "Z.toml", "a-extra.toml", "b-local.toml", "\u00e9t\u00e9.toml"]


@os_agnostic
def test_windows_paths_are_ordered_by_their_exact_names() -> None:
    ordered = in_dot_d_order(PureWindowsPath("C:/app/config.d", name) for name in _NAMES)

    assert [path.name for path in ordered] == _EXPECTED


@os_agnostic
def test_posix_paths_are_ordered_by_their_exact_names() -> None:
    ordered = in_dot_d_order(PurePosixPath("/etc/app/config.d", name) for name in _NAMES)

    assert [path.name for path in ordered] == _EXPECTED


@os_agnostic
def test_the_paths_come_back_unchanged() -> None:
    paths = [PureWindowsPath("C:/app/config.d", name) for name in _NAMES]

    assert sorted(in_dot_d_order(paths), key=str) == sorted(paths, key=str)
