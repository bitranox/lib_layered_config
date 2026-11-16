"""The stream ``display_config`` hands its Rich console answers for the real stdout and fits every write.

Rich decides colour from ``isatty``, its Windows console path from ``fileno`` and its box characters
from ``encoding``, so the fitting stream must answer each for the stream it writes to, looked up at
every call because a test's capture or a redirect replaces ``sys.stdout`` after the console is built.
"""

from __future__ import annotations

import sys

import pytest

from lib_layered_config.adapters._stream_text import FittedStream
from lib_layered_config.cli.output import emit_text
from tests.support.os_markers import os_agnostic

_KANJI = chr(0x6F22)
_UMLAUT = chr(0xFC)
_B = chr(92)


class _Cp1252Terminal:
    """A terminal stream with the given code page (cp1252 unless named) and descriptor 7."""

    def __init__(self, encoding: str = "cp1252") -> None:
        self.encoding = encoding
        self.written: list[str] = []
        self.flushed = 0

    def write(self, text: str) -> int:
        text.encode(self.encoding)  # raises as a real cp1252 stream would
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        self.flushed += 1

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return 7


@os_agnostic
@pytest.mark.parametrize("err", [False, True], ids=["stdout", "stderr"])
def test_the_stream_answers_for_its_target_and_fits_what_it_writes(monkeypatch: pytest.MonkeyPatch, err: bool) -> None:
    stream = FittedStream(err=err)
    target = _Cp1252Terminal()
    # sys.stdout / sys.stderr are the process's own streams, the edge this class exists to wrap.
    monkeypatch.setattr(sys, "stderr" if err else "stdout", target)

    written = stream.write(f"{_UMLAUT}{_KANJI}")
    stream.flush()

    assert (stream.encoding, stream.isatty(), stream.fileno()) == ("cp1252", True, 7)
    assert (written, target.written, target.flushed) == (2, [f"{_UMLAUT}{_B}u6f22"], 1)


@os_agnostic
def test_cli_text_on_stderr_is_fitted_to_stderr_not_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout, stderr = _Cp1252Terminal("utf-8"), _Cp1252Terminal()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    emit_text(_KANJI, err=True)

    assert ("".join(stderr.written), stdout.written) == (f"{_B}u6f22\n", [])
