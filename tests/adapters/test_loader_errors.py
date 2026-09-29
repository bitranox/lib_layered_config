"""A file that cannot be decoded or parsed is a library error naming the place, never the content."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import Config, ConfigError, read_config
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

_UTF16_BOM_LE = b"\xff\xfe"
_UTF16_BOM_BE = b"\xfe\xff"
_UTF32_BOM_LE = b"\xff\xfe\x00\x00"
_UTF32_BOM_BE = b"\x00\x00\xfe\xff"
#: A YAML document with a nested value, so a wrong decode (garbage or a different value) is
#: caught by the equality check rather than by luck matching a flat scalar.
_YAML_TEXT = "outer:\n  k: 1\n"
YAML_BOM_BODIES = {
    "utf-16-le": _UTF16_BOM_LE + _YAML_TEXT.encode("utf-16-le"),
    "utf-16-be": _UTF16_BOM_BE + _YAML_TEXT.encode("utf-16-be"),
    "utf-32-le": _UTF32_BOM_LE + _YAML_TEXT.encode("utf-32-le"),
    "utf-32-be": _UTF32_BOM_BE + _YAML_TEXT.encode("utf-32-be"),
}


def _chain(exc: BaseException) -> list[BaseException]:
    """Return every exception reachable from *exc* via ``__cause__`` OR ``__context__``.

    A breadth-first walk over both links: a loader that sets ``__cause__`` (``raise ... from
    exc``) still leaves the original in ``__context__`` too, so following only ``__cause__ or
    __context__`` misses whichever link a raise site did not choose.
    """
    seen: list[BaseException] = []
    queue: list[BaseException] = [exc]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.append(current)
        if current.__cause__ is not None:
            queue.append(current.__cause__)
        if current.__context__ is not None:
            queue.append(current.__context__)
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


def _read_config(path: Path) -> Config:
    where = {"dotenv_path": path} if path.suffix == ".env" else {"default_file": path}
    return read_config(vendor="Probe", app="Probe", slug="decode-probe", **where)


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
@pytest.mark.parametrize("suffix", sorted(MALFORMED))
def test_the_parse_failure_log_event_carries_no_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, suffix: str
) -> None:
    body, _ = MALFORMED[suffix]
    path = tmp_path / f"bad{suffix}"
    path.write_bytes(body)
    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(ConfigError):
        _read(path)
    # Liveness: the capture sees the event, so an absent marker means the event is clean, not unseen.
    assert any(record.getMessage() == "config_file_invalid" for record in caplog.records)
    assert not any(MARK.decode() in repr(vars(record)) for record in caplog.records)


@os_agnostic
@pytest.mark.parametrize("suffix", sorted(f for f in NOT_UTF8 if f != ".env"))
def test_the_decode_failure_log_event_carries_no_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, suffix: str
) -> None:
    body = NOT_UTF8[suffix]
    path = tmp_path / f"bad{suffix}"
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


@os_agnostic
@pytest.mark.parametrize("label", sorted(YAML_BOM_BODIES))
def test_a_bom_marked_utf16_or_utf32_yaml_file_loads(tmp_path: Path, label: str) -> None:
    path = tmp_path / "bom.yaml"
    path.write_bytes(YAML_BOM_BODIES[label])
    config = _read_config(path)
    assert config.get("outer.k") == 1


@os_agnostic
@pytest.mark.parametrize("suffix", [".toml", ".json"])
def test_a_utf16_toml_or_json_file_is_still_refused_as_not_valid_utf8(tmp_path: Path, suffix: str) -> None:
    text = 'k = "v"\n' if suffix == ".toml" else '{"k": "v"}'
    path = tmp_path / f"bom{suffix}"
    path.write_bytes(_UTF16_BOM_LE + text.encode("utf-16-le"))
    with pytest.raises(ConfigError) as caught:
        _read(path)
    assert f"{path} is not valid UTF-8" in str(caught.value)
    _assert_no_content(caught.value)


@os_agnostic
def test_a_truncated_utf16_yaml_body_is_refused_content_free(tmp_path: Path) -> None:
    text = "password: " + MARK.decode() + "\n"
    # A trailing odd byte truncates the last UTF-16 code unit, so the decode fails.
    body = _UTF16_BOM_LE + text.encode("utf-16-le") + b"\x41"
    path = tmp_path / "bad.yaml"
    path.write_bytes(body)
    with pytest.raises(ConfigError) as caught:
        _read(path)
    assert f"{path} is not valid UTF-16" in str(caught.value)
    assert MARK.decode() not in str(caught.value)
    _assert_no_content(caught.value)


@os_agnostic
def test_a_utf32_bom_yaml_body_that_does_not_decode_is_refused_content_free(tmp_path: Path) -> None:
    text = "password: " + MARK.decode() + "\n"
    # A trailing odd byte after a whole number of UTF-32 code units truncates the last one.
    body = _UTF32_BOM_LE + text.encode("utf-32-le") + b"\x41"
    path = tmp_path / "bad.yaml"
    path.write_bytes(body)
    with pytest.raises(ConfigError) as caught:
        _read(path)
    with pytest.raises(UnicodeDecodeError) as decode_error:
        body.decode("utf-32")
    offset = decode_error.value.start
    assert f"{path} is not valid UTF-32 (byte offset {offset})" in str(caught.value)
    assert MARK.decode() not in str(caught.value)
    _assert_no_content(caught.value)


@os_agnostic
def test_a_utf16_yaml_body_with_a_lone_surrogate_is_refused_content_free(tmp_path: Path) -> None:
    text = "password: " + MARK.decode() + "\n"
    lone_high_surrogate = b"\x00\xd8"  # 0xD800 in UTF-16LE, never followed by a low surrogate.
    body = _UTF16_BOM_LE + text.encode("utf-16-le") + lone_high_surrogate
    path = tmp_path / "bad.yaml"
    path.write_bytes(body)
    with pytest.raises(ConfigError) as caught:
        _read(path)
    with pytest.raises(UnicodeDecodeError) as decode_error:
        body.decode("utf-16")
    offset = decode_error.value.start
    assert f"{path} is not valid UTF-16 (byte offset {offset})" in str(caught.value)
    assert MARK.decode() not in str(caught.value)
    _assert_no_content(caught.value)
