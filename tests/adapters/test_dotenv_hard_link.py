"""The upward ``.env`` search passes over a file with more than one hard link.

The owner check trusts a file the reader owns. A hard link keeps that owner: another user who can
write some file the reader owns (a group- or world-writable one, on the same filesystem) can link
it as ``.env`` into a directory on the search path and then write settings into it. A second link
is the one trace that leaves, so the search skips such a file (user decision 2026-11-17,
rs-R4-F1). A file the caller named (``dotenv_path``) is the caller's choice and is loaded anyway.

Real hard links, no faked stat: the link count is what the check reads.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from lib_layered_config import read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _linked_dotenv(directory: Path, content: str = "KEY=linked\n") -> Path:
    """Write ``directory/.env`` with a second hard link beside it, and return the ``.env``."""
    elsewhere = directory / "owned-elsewhere.txt"
    elsewhere.write_text(content, encoding="utf-8")
    dotenv = directory / ".env"
    os.link(elsewhere, dotenv)
    assert dotenv.stat().st_nlink == 2
    return dotenv


@os_agnostic
def test_the_search_skips_a_hard_linked_dotenv_and_goes_on_upward(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("KEY=parent\n", encoding="utf-8")
    start = tmp_path / "project"
    start.mkdir()
    _linked_dotenv(start)

    loader = DefaultDotEnvLoader()

    loaded = loader.load(start)

    assert loaded.data == {"key": "parent"}
    assert loaded.path == tmp_path / ".env"


@os_agnostic
def test_a_skipped_hard_link_is_logged_as_a_warning_naming_file_and_link_count(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    linked = _linked_dotenv(tmp_path)

    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"):
        assert DefaultDotEnvLoader().load(tmp_path).data == {}

    skipped = [record for record in caplog.records if record.message == "dotenv_skipped_hard_link"]
    assert [record.levelno for record in skipped] == [logging.WARNING]
    context = skipped[0].__dict__["context"]
    assert (context["path"], context["link_count"]) == (str(linked), 2)


@os_agnostic
def test_a_dotenv_with_one_link_still_loads(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("KEY=single\n", encoding="utf-8")

    assert DefaultDotEnvLoader().load(tmp_path).data == {"key": "single"}


@os_agnostic
def test_a_named_dotenv_path_loads_although_it_has_two_links(tmp_path: Path) -> None:
    linked = _linked_dotenv(tmp_path)

    assert DefaultDotEnvLoader().load(dotenv_path=linked).data == {"key": "linked"}


@posix_only
def test_a_symlink_to_a_hard_linked_file_is_skipped_too(tmp_path: Path) -> None:
    # The link count is read through the symlink: the planted file is what the search would read.
    store = tmp_path / "store"
    store.mkdir()
    target = _linked_dotenv(store)
    start = tmp_path / "project"
    start.mkdir()
    (start / ".env").symlink_to(target)

    assert DefaultDotEnvLoader().load(start).data == {}


@os_agnostic
def test_read_config_leaves_a_hard_linked_dotenv_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _linked_dotenv(tmp_path, "SERVICE__TIMEOUT=99\n")

    config = read_config(vendor="Acme", app="Demo", slug="demo-hard-link", start_dir=str(tmp_path))

    assert config.get("service.timeout") is None
