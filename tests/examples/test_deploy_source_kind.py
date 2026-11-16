"""A deploy source that is not a regular file is refused with a message saying what it is.

Every such source used to read "Configuration source not found", even a directory that plainly exists.
User decision 2026-11-16 (A6): keep ``FileNotFoundError`` (the CLI exit code stays 2) and word the
message by kind; a missing path keeps the old text exactly.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.deploy import deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path


def _refusal(source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    sandbox = create_layered_sandbox(tmp_path / "root", vendor="Acme", app="Demo", slug="demo")
    sandbox.apply_env(monkeypatch)
    with pytest.raises(FileNotFoundError) as caught:
        deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], set_permissions=False)
    assert not (sandbox.roots["user"] / "config.toml").exists()
    return str(caught.value)


@os_agnostic
def test_a_missing_source_keeps_the_not_found_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "absent.toml"

    assert _refusal(source, tmp_path, monkeypatch) == f"Configuration source not found: {source}"


@os_agnostic
def test_a_directory_source_is_named_a_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "config.toml"
    source.mkdir()

    assert _refusal(source, tmp_path, monkeypatch) == f"Configuration source is a directory, not a file: {source}"


@posix_only
def test_a_fifo_source_is_named_not_a_regular_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert sys.platform != "win32"  # posix_only; tells the checker os.mkfifo exists here
    source = tmp_path / "config.toml"
    os.mkfifo(source)

    assert _refusal(source, tmp_path, monkeypatch) == f"Configuration source is not a regular file: {source}"


@posix_only
def test_a_dangling_link_source_is_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "config.toml"
    source.symlink_to(tmp_path / "nowhere.toml")

    assert _refusal(source, tmp_path, monkeypatch) == f"Configuration source not found: {source}"
