"""A deploy that fails mid-write leaves the destination as it was, with or without permission setting.

The write goes to a temp file beside the destination and is renamed into place, so a reader sees the
old file or the whole new one. With permission setting off, the new file keeps the old one's mode,
and a destination a rename would change (hard links, another owner, its own extended attributes)
is still rewritten in place.

The failures are real: a child interpreter caps its own file size (RLIMIT_FSIZE), so the write fails
with EFBIG exactly where a full disk would make it fail.
"""

from __future__ import annotations

import os
import stat
import struct
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.deploy import DeployAction, deploy_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
_LIMIT = 64 * 1024
_OLD = "keep = 'the old config'\n"
_NEW = "x = 1\n"

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="extended attributes are read on Linux only")


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    home = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    return home


def _destination(sandbox: LayeredSandbox) -> Path:
    path = sandbox.roots["user"] / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _source(tmp_path: Path, text: str) -> Path:
    source = tmp_path / "source.toml"
    source.write_text(text, encoding="utf-8")
    return source


def _deploy_capped(source: Path, *, set_permissions: bool) -> str:
    """Run a forced user deploy of *source* in a child whose files may not grow past ``_LIMIT``."""
    env = {**os.environ, "PROBE_SOURCE": str(source), "PROBE_LIMIT": str(_LIMIT)}
    env["PROBE_PERMISSIONS"] = "1" if set_permissions else "0"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, resource, signal\n"
            "from pathlib import Path\n"
            "from lib_layered_config import deploy_config\n"
            "signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n"
            "limit = int(os.environ['PROBE_LIMIT'])\n"
            "resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))\n"
            "try:\n"
            "    deploy_config(Path(os.environ['PROBE_SOURCE']), vendor='Acme', app='Demo', slug='demo',\n"
            "                  targets=['user'], force=True, set_permissions=os.environ['PROBE_PERMISSIONS'] == '1')\n"
            "except OSError as exc:\n"
            "    print('refused', exc.errno)\n"
            "else:\n"
            "    print('deployed')\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _large(tmp_path: Path) -> Path:
    return _source(tmp_path, _NEW + "# padding\n" * (2 * _LIMIT // 10))


@posix_only
@pytest.mark.parametrize("set_permissions", [False, True], ids=["no-permissions", "permissions"])
def test_a_failed_overwrite_leaves_the_old_config_whole(
    sandbox: LayeredSandbox, tmp_path: Path, *, set_permissions: bool
) -> None:
    destination = _destination(sandbox)
    destination.write_text(_OLD, encoding="utf-8")

    outcome = _deploy_capped(_large(tmp_path), set_permissions=set_permissions)

    assert outcome == "refused 27"
    assert destination.read_text(encoding="utf-8") == _OLD
    # The destination is unchanged, so the backup --force took is removed, and no temp file is left.
    assert sorted(p.name for p in destination.parent.iterdir()) == ["config.toml"]


@posix_only
def test_a_failed_first_write_leaves_no_partial_file(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    destination = _destination(sandbox)

    outcome = _deploy_capped(_large(tmp_path), set_permissions=False)

    assert outcome == "refused 27"
    assert list(destination.parent.iterdir()) == []


@posix_only
def test_a_failed_backup_leaves_no_partial_backup(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    # The existing file is larger than the child may write, so copying it to config.toml.bak fails.
    destination = _destination(sandbox)
    old = _OLD + "# padding\n" * (2 * _LIMIT // 10)
    destination.write_text(old, encoding="utf-8")

    outcome = _deploy_capped(_source(tmp_path, _NEW), set_permissions=False)

    assert outcome == "refused 27"
    assert destination.read_text(encoding="utf-8") == old
    assert [p.name for p in destination.parent.iterdir()] == ["config.toml"]


def _force_without_permissions(source: Path) -> DeployAction:
    (result,) = deploy_config(
        source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"], force=True, set_permissions=False
    )
    return result.action


@posix_only
def test_without_permissions_an_overwrite_keeps_the_mode_and_replaces_the_file(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    destination = _destination(sandbox)
    destination.write_text(_OLD, encoding="utf-8")
    destination.chmod(0o640)
    old_inode = destination.stat().st_ino

    action = _force_without_permissions(_source(tmp_path, _NEW))

    assert action is DeployAction.OVERWRITTEN
    assert destination.read_text(encoding="utf-8") == _NEW
    assert stat.S_IMODE(destination.stat().st_mode) == 0o640
    assert destination.stat().st_ino != old_inode


@posix_only
def test_without_permissions_a_new_file_gets_the_mode_a_plain_create_gives(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    destination = _destination(sandbox)
    plain = destination.parent / "plain"
    plain.write_text("", encoding="utf-8")

    action = _force_without_permissions(_source(tmp_path, _NEW))

    assert action is DeployAction.CREATED
    assert stat.S_IMODE(destination.stat().st_mode) == stat.S_IMODE(plain.stat().st_mode)


@os_agnostic
def test_a_hard_linked_destination_is_rewritten_in_place(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    destination = _destination(sandbox)
    destination.write_text(_OLD, encoding="utf-8")
    other = tmp_path / "other-name.toml"
    os.link(destination, other)

    _force_without_permissions(_source(tmp_path, _NEW))

    assert other.read_text(encoding="utf-8") == _NEW
    assert destination.samefile(other)


@os_agnostic
def test_a_read_only_destination_is_refused_not_replaced(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    # The directory is writable, so a rename would replace a file its owner made read-only.
    if sys.platform != "win32" and os.geteuid() == 0:
        pytest.skip("root writes a file with mode 0o444 anyway")
    destination = _destination(sandbox)
    destination.write_text(_OLD, encoding="utf-8")
    destination.chmod(0o444)
    old_inode = destination.stat().st_ino

    try:
        with pytest.raises(PermissionError) as caught:
            _force_without_permissions(_source(tmp_path, _NEW))

        assert destination.read_text(encoding="utf-8") == _OLD
        assert destination.stat().st_ino == old_inode
        # On Windows the temp took the read-only attribute, so removing it failed: it stayed
        # behind and its error, naming the temp, replaced the refusal of the destination.
        assert caught.value.filename == str(destination)
        assert [p.name for p in destination.parent.iterdir() if p.name.endswith(".tmp")] == []
    finally:
        destination.chmod(stat.S_IREAD | stat.S_IWRITE)


_NO_ID = 0xFFFFFFFF


def _acl(*named_user_perms: int) -> bytes:
    """A POSIX ACL as Linux stores it: owner rw, group r, other r, one named user per perm, a mask."""
    entries = [(0x01, 6, _NO_ID), *((0x02, perm, 65534) for perm in named_user_perms), (0x04, 4, _NO_ID)]
    entries += [(0x10, 6, _NO_ID), (0x20, 4, _NO_ID)]
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)


def _set_acl(path: Path, name: str, value: bytes) -> None:
    if sys.platform != "linux":
        pytest.skip("extended attributes are read on Linux only")
    try:
        os.setxattr(path, name, value)
    except OSError as exc:
        pytest.skip(f"the file system keeps no POSIX ACL here: {exc}")


def _xattrs_of(path: Path) -> dict[str, bytes]:
    if sys.platform != "linux":
        pytest.skip("extended attributes are read on Linux only")
    return {name: os.getxattr(path, name) for name in os.listxattr(path)}


@posix_only
@linux_only
@pytest.mark.parametrize(
    "own_acl",
    [_acl(6), None],
    ids=["own-acl-differs-from-the-default", "no-acl-where-the-default-would-add-one"],
)
def test_a_destination_whose_acl_a_rename_would_change_is_rewritten_in_place(
    sandbox: LayeredSandbox, tmp_path: Path, own_acl: bytes | None
) -> None:
    destination = _destination(sandbox)
    destination.write_text(_OLD, encoding="utf-8")
    _set_acl(destination.parent, "system.posix_acl_default", _acl(4))
    if own_acl is not None:
        _set_acl(destination, "system.posix_acl_access", own_acl)
    before = _xattrs_of(destination)
    old_inode = destination.stat().st_ino

    _force_without_permissions(_source(tmp_path, _NEW))

    assert destination.read_text(encoding="utf-8") == _NEW
    assert destination.stat().st_ino == old_inode
    assert _xattrs_of(destination) == before


@posix_only
@linux_only
def test_a_destination_holding_the_directory_default_acl_is_replaced(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    # Created under the default ACL, the file has exactly what a fresh file gets once that has its
    # mode, so the rename changes nothing: "any extended attribute keeps it in place" would send it
    # down the torn path. Its mode differs from what a create gives, and a chmod rewrites the ACL's
    # mask entry, so the comparison must come after the temp file has taken the mode.
    destination = _destination(sandbox)
    _set_acl(destination.parent, "system.posix_acl_default", _acl(4))
    destination.write_text(_OLD, encoding="utf-8")
    destination.chmod(0o640)
    assert _xattrs_of(destination)
    old_inode = destination.stat().st_ino

    _force_without_permissions(_source(tmp_path, _NEW))

    assert destination.read_text(encoding="utf-8") == _NEW
    assert destination.stat().st_ino != old_inode
