"""A refused configuration file is reported once, by the exception, never by an ERROR record too.

Every refusal raises a ``ConfigError`` naming the path, and the caller decides how loud to be. A
caller that catches it and carries on (a deploy that overwrites a broken user file) must not find
an ``[ERRO]`` line from the library on stderr for a run that succeeded. The event is still logged,
at DEBUG, so debug logging shows which file was refused and why.
"""

from __future__ import annotations

import logging
import os
import stat
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ConfigError, read_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_VENDOR, _APP, _SLUG = "Acme", "ConfigKit", "config-kit"

# Root bypasses file permissions, so no unreadable file can be built while running as root.
_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=_VENDOR, app=_APP, slug=_SLUG)
    created.apply_env(monkeypatch)
    return created


def _read(*, default_file: Path | None = None, dotenv_path: Path | None = None) -> None:
    read_config(vendor=_VENDOR, app=_APP, slug=_SLUG, default_file=default_file, dotenv_path=dotenv_path)


def _refused_records(caplog: pytest.LogCaptureFixture, read: Callable[[], None]) -> list[logging.LogRecord]:
    """Run *read*, require the refusal, and return every record the library logged meanwhile."""
    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(ConfigError):
        read()
    return [record for record in caplog.records if record.name.startswith("lib_layered_config")]


def _assert_logged_only_at_debug(records: list[logging.LogRecord], event: str) -> None:
    levels = [record.levelname for record in records if record.getMessage() == event]
    # Liveness: the event is captured, so its level is measured rather than missed.
    assert levels == ["DEBUG"], (event, levels)
    loud = [(record.getMessage(), record.levelname) for record in records if record.levelno >= logging.WARNING]
    assert loud == []


@os_agnostic
def test_an_invalid_toml_file_is_logged_at_debug(caplog: pytest.LogCaptureFixture, sandbox: LayeredSandbox) -> None:
    path = sandbox.write("user", "config.toml", content="this is [not valid toml\n")
    records = _refused_records(caplog, lambda: _read(default_file=path))
    _assert_logged_only_at_debug(records, "config_file_invalid")


@os_agnostic
def test_an_undecodable_file_is_logged_at_debug(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    path = tmp_path / "defaults.json"
    path.write_bytes(b'{"a": "\xff"}')
    records = _refused_records(caplog, lambda: _read(default_file=path))
    _assert_logged_only_at_debug(records, "config_file_invalid")


@os_agnostic
def test_a_directory_named_as_the_dotenv_file_is_logged_at_debug(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, sandbox: LayeredSandbox
) -> None:
    folder = tmp_path / "env-dir"
    folder.mkdir()
    records = _refused_records(caplog, lambda: _read(dotenv_path=folder))
    _assert_logged_only_at_debug(records, "config_path_is_directory")


@posix_only
def test_a_fifo_named_as_the_default_file_is_logged_at_debug(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, sandbox: LayeredSandbox
) -> None:
    fifo = tmp_path / "defaults.toml"
    os.mkfifo(fifo)
    records = _refused_records(caplog, lambda: _read(default_file=fifo))
    _assert_logged_only_at_debug(records, "config_path_is_special_file")


@os_agnostic
def test_a_default_file_of_unsupported_format_is_logged_at_debug(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, sandbox: LayeredSandbox
) -> None:
    path = tmp_path / "defaults.conf"
    path.write_text("a = 1\n", encoding="utf-8")
    records = _refused_records(caplog, lambda: _read(default_file=path))
    _assert_logged_only_at_debug(records, "config_path_unsupported_format")


@posix_only
@pytest.mark.skipif(_RUNS_AS_ROOT, reason="root bypasses file permissions")
def test_an_unreadable_default_file_is_logged_at_debug(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, sandbox: LayeredSandbox
) -> None:
    path = tmp_path / "defaults.toml"
    path.write_text("a = 1\n", encoding="utf-8")
    path.chmod(0)
    try:
        records = _refused_records(caplog, lambda: _read(default_file=path))
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    _assert_logged_only_at_debug(records, "config_path_unreadable")


@os_agnostic
def test_a_malformed_dotenv_line_is_logged_at_debug(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, sandbox: LayeredSandbox
) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text("INVALID\n", encoding="utf-8")
    records = _refused_records(caplog, lambda: _read(dotenv_path=env_file))
    _assert_logged_only_at_debug(records, "dotenv_invalid_line")
