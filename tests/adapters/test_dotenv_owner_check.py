"""The upward ``.env`` search loads only a file the current user or root owns.

Another user can plant ``/tmp/.env``, and every program started below ``/tmp`` would otherwise load
it and let it outrank the app, host and user files. A file the caller named (``dotenv_path``) is
the caller's choice and is loaded whoever owns it.

The tests fake the effective uid at ``os.geteuid``: an unprivileged test cannot create a file some
other user owns, and the uid is the OS edge the check reads.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from lib_layered_config.adapters.dotenv.default import (
    DefaultDotEnvLoader,
    _owner_is_trusted,  # pyright: ignore[reportPrivateUsage] - unit test of the owner trust rule over a uid table
)
from tests.support.os_markers import os_agnostic, posix_only


def _plant_dotenv(tmp_path: Path) -> tuple[Path, Path]:
    """Write ``tmp_path/.env`` and return it with a start directory below it."""
    planted = tmp_path / ".env"
    planted.write_text("KEY=planted\n", encoding="utf-8")
    start = tmp_path / "project"
    start.mkdir()
    return planted, start


def _become_another_user(monkeypatch: pytest.MonkeyPatch, owner_uid: int) -> int:
    """Make the process look like a user who neither owns the file nor is root."""
    if owner_uid == 0:
        pytest.skip("the test files are root-owned, and root-owned files are trusted")
    other = owner_uid + 1
    monkeypatch.setattr(os, "geteuid", lambda: other)
    return other


@posix_only
def test_upward_search_skips_a_dotenv_another_user_owns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    planted, start = _plant_dotenv(tmp_path)
    _become_another_user(monkeypatch, planted.stat().st_uid)

    loader = DefaultDotEnvLoader()

    assert loader.load(str(start)) == {}
    assert loader.last_loaded_path is None


@posix_only
def test_skipped_dotenv_is_logged_as_a_warning_naming_file_and_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    planted, start = _plant_dotenv(tmp_path)
    owner = planted.stat().st_uid
    _become_another_user(monkeypatch, owner)

    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"):
        DefaultDotEnvLoader().load(str(start))

    skipped = [record for record in caplog.records if record.message == "dotenv_skipped_foreign_owner"]
    assert [record.levelno for record in skipped] == [logging.WARNING]
    context = skipped[0].__dict__["context"]
    assert (context["path"], context["owner_uid"]) == (str(planted), owner)


@posix_only
def test_a_dotenv_in_both_the_walk_and_the_extras_is_checked_and_reported_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The resolver's search list walks upward from start_dir too, so read_config hands the loader
    # extras that repeat its own walk; each file must still be judged once.
    planted, start = _plant_dotenv(tmp_path)
    _become_another_user(monkeypatch, planted.stat().st_uid)

    with caplog.at_level(logging.WARNING, logger="lib_layered_config"):
        DefaultDotEnvLoader(extras=[str(planted)]).load(str(start))

    skipped = [record for record in caplog.records if record.message == "dotenv_skipped_foreign_owner"]
    assert len(skipped) == 1


@posix_only
def test_explicit_dotenv_path_loads_whoever_owns_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    planted, _start = _plant_dotenv(tmp_path)
    _become_another_user(monkeypatch, planted.stat().st_uid)

    assert DefaultDotEnvLoader().load(dotenv_path=str(planted)) == {"key": "planted"}


@posix_only
def test_a_symlink_the_user_does_not_own_is_passed_over_even_when_its_target_is_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The link is ours and its target, /etc/passwd, is root's. Seen as root (faked), the target is
    # trusted and the link is not, so only a check of the LINK's owner skips it. Judged by the
    # target alone, /etc/passwd would be parsed as a .env and refused as malformed.
    target = Path("/etc/passwd")
    if not target.is_file() or target.stat().st_uid != 0:
        pytest.skip("needs a root-owned /etc/passwd")
    link = tmp_path / ".env"
    link.symlink_to(target)
    link_owner = link.lstat().st_uid
    if link_owner == 0:
        pytest.skip("the test files are root-owned, and root-owned files are trusted")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    start = tmp_path / "project"
    start.mkdir()

    loader = DefaultDotEnvLoader()

    assert loader.load(str(start)) == {}
    assert loader.last_loaded_path is None


@posix_only
def test_upward_search_loads_a_dotenv_the_current_user_owns(tmp_path: Path) -> None:
    _planted, start = _plant_dotenv(tmp_path)

    assert DefaultDotEnvLoader().load(str(start)) == {"key": "planted"}


@os_agnostic
@pytest.mark.parametrize(
    ("owner_uid", "euid", "trusted"),
    [
        (1000, 1000, True),
        (0, 1000, True),
        (0, 0, True),
        (1001, 1000, False),
        (1000, 0, False),
    ],
    ids=["own-file", "root-file", "root-reads-root-file", "other-user", "root-reads-user-file"],
)
def test_owner_is_trusted_accepts_only_the_current_user_and_root(owner_uid: int, euid: int, trusted: bool) -> None:
    assert _owner_is_trusted(owner_uid, euid=euid) is trusted
