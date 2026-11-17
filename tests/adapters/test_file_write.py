"""When a deployed file must be rewritten in place rather than replaced by a rename.

A rename gives the file a new inode: every hard link, the owner and group, and every extended
attribute (a POSIX ACL, an SELinux label) of the old inode are gone, and the new file has what a
fresh file in that directory gets. ``must_write_in_place`` says when that would change the file.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from lib_layered_config.adapters import _file_write as file_write_module
from lib_layered_config.adapters._file_write import FileFacts, must_write_in_place, write_file
from tests.support.os_markers import os_agnostic, posix_only

_ACL = "system.posix_acl_access"
_LABEL = "security.selinux"
_BASE = FileFacts(links=1, uid=1000, gid=1000, writable=True, xattrs={_LABEL: b"user_home_t"})


@os_agnostic
def test_a_file_a_rename_would_not_change_is_replaced() -> None:
    assert must_write_in_place(_BASE, dataclasses.replace(_BASE)) is False


@os_agnostic
@pytest.mark.parametrize(
    "target",
    [
        dataclasses.replace(_BASE, links=2),
        dataclasses.replace(_BASE, uid=0),
        dataclasses.replace(_BASE, gid=0),
        dataclasses.replace(_BASE, writable=False),
        dataclasses.replace(_BASE, xattrs=None),
    ],
    ids=["hard-linked", "other-owner", "other-group", "not-writable", "attributes-unreadable"],
)
def test_a_file_a_rename_would_change_is_written_in_place(target: FileFacts) -> None:
    assert must_write_in_place(target, _BASE) is True


@os_agnostic
def test_attributes_a_fresh_file_cannot_report_keep_the_file_in_place() -> None:
    assert must_write_in_place(_BASE, dataclasses.replace(_BASE, xattrs=None)) is True


@os_agnostic
@pytest.mark.parametrize(
    "target_xattrs, fresh_xattrs",
    [
        ({_LABEL: b"user_home_t", _ACL: b"own"}, {_LABEL: b"user_home_t"}),
        ({_LABEL: b"user_home_t"}, {_LABEL: b"user_home_t", _ACL: b"directory default"}),
        ({_LABEL: b"user_home_t", _ACL: b"own"}, {_LABEL: b"user_home_t", _ACL: b"directory default"}),
        ({_LABEL: b"etc_t"}, {_LABEL: b"user_home_t"}),
    ],
    ids=["own-acl-a-rename-drops", "default-acl-a-rename-adds", "same-name-other-value", "other-label"],
)
def test_any_attribute_difference_keeps_the_file_in_place(
    target_xattrs: dict[str, bytes], fresh_xattrs: dict[str, bytes]
) -> None:
    # A rename that adds the directory's default ACL widens access as surely as one that drops the
    # file's own; and a names-only comparison would replace a file whose own ACL differs.
    target = dataclasses.replace(_BASE, xattrs=target_xattrs)
    fresh = dataclasses.replace(_BASE, xattrs=fresh_xattrs)

    assert must_write_in_place(target, fresh) is True


@posix_only
@pytest.mark.parametrize(("restrict", "expected"), [(True, 0o600), (False, 0o644)], ids=["restrict", "plain"])
def test_permission_setting_creates_the_new_file_owner_only(tmp_path: Path, *, restrict: bool, expected: int) -> None:
    """With permission setting on, the file is owner-only from its creation, before the caller's chmod.

    A permissive umask (0o022) shows the difference: a file created at 0o666 would be readable by
    everyone between the write and the chmod that follows it.
    """
    source = tmp_path / "source.toml"
    source.write_text("token = 'secret'\n", encoding="utf-8")
    target = tmp_path / "config.toml"

    old_umask = os.umask(0o022)
    try:
        write_file(target, source, restrict=restrict, chunk_bytes=64 * 1024)
    finally:
        os.umask(old_umask)

    assert (target.read_text(encoding="utf-8"), target.stat().st_mode & 0o777) == ("token = 'secret'\n", expected)


def _open_descriptors() -> int | None:
    """How many descriptors this process has open, where the OS lists them (Linux /proc); None elsewhere."""
    fd_dir = Path("/proc/self/fd")
    return len(list(fd_dir.iterdir())) if fd_dir.is_dir() else None


@os_agnostic
def test_a_failed_access_list_copy_closes_the_temp_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # copy_dacl wraps the Windows security API, the edge that can refuse (a share without WRITE_DAC, an
    # unreadable access list); an open temp handle there blocks its own delete on Windows.
    def refuse(_source: Path, _target: Path) -> None:
        raise PermissionError("cannot read the access list")

    monkeypatch.setattr(file_write_module, "copy_dacl", refuse)
    destination = tmp_path / "config.toml"
    destination.write_text("a = 1\n", encoding="utf-8")
    source = tmp_path / "source.toml"
    source.write_text("a = 2\n", encoding="utf-8")
    before = _open_descriptors()

    for _ in range(3):
        with pytest.raises(PermissionError):
            write_file(destination, source, restrict=False, chunk_bytes=4096)

    assert _open_descriptors() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.toml", "source.toml"]
    assert destination.read_text(encoding="utf-8") == "a = 1\n"
