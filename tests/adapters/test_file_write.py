"""When a deployed file must be rewritten in place rather than replaced by a rename.

A rename gives the file a new inode: every hard link, the owner and group, and every extended
attribute (a POSIX ACL, an SELinux label) of the old inode are gone, and the new file has what a
fresh file in that directory gets. ``must_write_in_place`` says when that would change the file.
"""

from __future__ import annotations

import dataclasses

import pytest

from lib_layered_config.adapters._file_write import FileFacts, must_write_in_place
from tests.support.os_markers import os_agnostic

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
