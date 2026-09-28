"""A file that cannot be decoded or parsed is a library error naming the place, never the content."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ConfigError, read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

MARK = b"secretmarker"
NOT_UTF8 = {
    ".env": b"KEY_A=ok\nSECRET=" + MARK + b"\xff" + MARK + b"\n",
    ".toml": b'secret = "' + MARK + b"\xff" + MARK + b'"\n',
    ".json": b'{"secret": "' + MARK + b"\xff" + MARK + b'"}',
    ".yaml": b"secret: " + MARK + b"\xff" + MARK + b"\n",
}
#: Well-encoded but malformed: the marker sits on the line the parser complains about.
MALFORMED = {
    ".toml": (b'ok = 1\nsecret = "' + MARK + b"\n", "TOML"),
    ".json": (b'{"ok": 1,\n "secret": ' + MARK + b"}", "JSON"),
    ".yaml": (b"ok: 1\npassword: " + MARK + b": x\n", "YAML"),
}
PARSER_ERRORS = ("TomlParsingError", "JSONDecodeError", "YAMLError", "MarkedYAMLError", "ScannerError")


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def _assert_no_content(exc: BaseException) -> None:
    for link in _chain(exc):
        assert MARK.decode() not in str(link)
        assert not isinstance(link, UnicodeDecodeError)
        assert not any(cls.__name__ in PARSER_ERRORS for cls in type(link).__mro__)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Points every platform's app/host/user roots into tmp_path (Linux, macOS and Windows variables).
    create_layered_sandbox(tmp_path / "layers", vendor="Probe", app="Probe", slug="decode-probe").apply_env(monkeypatch)
    monkeypatch.chdir(tmp_path)


def _read(path: Path) -> None:
    where = {"dotenv_path": path} if path.suffix == ".env" else {"default_file": path}
    read_config(vendor="Probe", app="Probe", slug="decode-probe", **where)


@os_agnostic
@pytest.mark.parametrize("suffix", sorted(NOT_UTF8))
def test_a_non_utf8_file_names_the_file_line_and_offset(tmp_path: Path, suffix: str) -> None:
    body = NOT_UTF8[suffix]
    path = tmp_path / f"bad{suffix}"
    path.write_bytes(body)
    with pytest.raises(ConfigError) as caught:
        _read(path)
    offset = body.index(b"\xff")
    line = body.count(b"\n", 0, offset) + 1
    assert f"{path} is not valid UTF-8 (line {line}, byte offset {offset})" in str(caught.value)
    _assert_no_content(caught.value)


@os_agnostic
@pytest.mark.parametrize("suffix", sorted(MALFORMED))
def test_a_malformed_file_names_the_file_format_and_line(tmp_path: Path, suffix: str) -> None:
    body, format_name = MALFORMED[suffix]
    path = tmp_path / f"bad{suffix}"
    path.write_bytes(body)
    with pytest.raises(ConfigError) as caught:
        _read(path)
    pattern = rf"{re.escape(str(path))} is not valid {format_name} \(line 2, column \d+\)$"
    assert re.search(pattern, str(caught.value)), str(caught.value)
    _assert_no_content(caught.value)


@os_agnostic
def test_the_parse_failure_log_event_carries_no_content(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    body, _ = MALFORMED[".yaml"]
    path = tmp_path / "bad.yaml"
    path.write_bytes(body)
    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(ConfigError):
        _read(path)
    # Liveness: the capture sees the event, so an absent marker means the event is clean, not unseen.
    assert any(record.getMessage() == "config_file_invalid" for record in caplog.records)
    assert not any(MARK.decode() in repr(vars(record)) for record in caplog.records)


@os_agnostic
def test_the_dotenv_loader_raises_its_documented_error(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_bytes(NOT_UTF8[".env"])
    with pytest.raises(InvalidFormatError, match=r"is not valid UTF-8 \(line 2, byte offset 28\)$"):
        DefaultDotEnvLoader().load(dotenv_path=str(path))
