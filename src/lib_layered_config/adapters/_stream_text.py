r"""Fit text to the stream it is written to, so writing it never raises ``UnicodeEncodeError``.

A piped stdout on Windows uses the ANSI code page (cp1252 on a German or English install), which has
no CJK characters and no emoji, so printing such a configuration value raised
``UnicodeEncodeError``: the CLI exited with nothing on stdout, a ``--json`` envelope included, and
``display_config`` stopped part-way. Output is therefore fitted to the stream's own encoding before
it is written:

- JSON text writes each character the stream cannot encode as a ``\uXXXX`` escape (a surrogate pair
  above U+FFFF). Non-ASCII characters in JSON text occur only inside strings, so the result is valid
  JSON that parses back to the same value.
- Human text writes each such character as a Python backslash escape (``errors="backslashreplace"``).

A character the stream can encode is written as it is, so a UTF-8 stream, and a cp1252 stream
printing umlauts, get exactly the text they got before. Forcing UTF-8 instead was rejected: it
would turn umlauts a cp1252 console shows correctly today into mojibake.

The JSON escape runs as a registered codec error handler, so the common path stays inside the codec
rather than a per-character Python loop.

Contents:
    - :func:`fit_json` / :func:`fit_text`: text fitted to a stream's encoding.
    - :class:`FittedStream` / :func:`fitted_console_file`: a text stream for a Rich ``Console``
      that fits every write.
"""

from __future__ import annotations

import codecs
import sys
from typing import IO, TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from typing import TextIO

__all__ = ["FittedStream", "fit_json", "fit_text", "fitted_console_file"]

_JSON_ESCAPE: Final[str] = "lib_layered_config.json_escape"
_BACKSLASH_ESCAPE: Final[str] = "backslashreplace"
# The highest code point a single JSON \u escape can carry; above it, a surrogate pair.
_BMP_MAX: Final[int] = 0xFFFF


def _json_escape_char(char: str) -> str:
    r"""Return *char* as a JSON ``\u`` escape, a surrogate pair above U+FFFF.

    Examples:
        >>> _json_escape_char(chr(0x6F22))
        '\\u6f22'
        >>> _json_escape_char(chr(0x1F600))
        '\\ud83d\\ude00'
    """
    code = ord(char)
    if code <= _BMP_MAX:
        return f"\\u{code:04x}"
    code -= 0x10000
    return f"\\u{0xD800 + (code >> 10):04x}\\u{0xDC00 + (code & 0x3FF):04x}"


def _json_escape(error: UnicodeError) -> tuple[str, int]:
    """Codec error handler: replace the characters *error* names with JSON escapes.

    Raises:
        UnicodeError: *error* is not an encode error (the handler is registered for encoding only).
    """
    if not isinstance(error, UnicodeEncodeError):
        raise error
    replacement = "".join(_json_escape_char(char) for char in error.object[error.start : error.end])
    return replacement, error.end


codecs.register_error(_JSON_ESCAPE, _json_escape)


def _stream_encoding(stream: object) -> str:
    """Return the encoding *stream* names, UTF-8 when it names none."""
    encoding: object = getattr(stream, "encoding", None)
    return encoding if isinstance(encoding, str) and encoding else "utf-8"


def _fit_to_encoding(text: str, encoding: str, *, errors: str) -> str:
    r"""Return *text* with every character *encoding* cannot encode replaced per *errors*.

    An encoding Python does not know leaves *text* unchanged, for the stream to report as it would
    have before.

    Examples:
        >>> fitted = _fit_to_encoding("a" + chr(0xFC) + chr(0x6F22), "cp1252", errors="backslashreplace")
        >>> fitted == "a" + chr(0xFC) + "\\u6f22"
        True
        >>> _fit_to_encoding(chr(0x1F600), "cp1252", errors=_JSON_ESCAPE)
        '\\ud83d\\ude00'
        >>> _fit_to_encoding(chr(0x1F600), "utf-8", errors=_JSON_ESCAPE) == chr(0x1F600)
        True
    """
    try:
        return text.encode(encoding, errors).decode(encoding)
    except LookupError:
        return text


def fit_json(text: str, stream: object) -> str:
    """Return JSON *text* with what *stream* cannot encode written as ``\\uXXXX`` escapes."""
    return _fit_to_encoding(text, _stream_encoding(stream), errors=_JSON_ESCAPE)


def fit_text(text: str, stream: object) -> str:
    """Return human *text* with what *stream* cannot encode written as Python backslash escapes."""
    return _fit_to_encoding(text, _stream_encoding(stream), errors=_BACKSLASH_ESCAPE)


class FittedStream:
    """Write human text to the current ``sys.stdout`` (or ``sys.stderr``), fitted to its encoding.

    Made for a Rich ``Console``, which writes ``str`` to its file and raises on a character the
    stream cannot encode. The target is looked up at every call, as a ``Console`` built without a
    file does, so a stream replaced after construction (a test's capture, a redirect) is the one
    written to. ``encoding``, ``isatty`` and ``fileno`` answer for the target, so Rich decides
    colour, width and the Windows console path exactly as it would for the target itself.
    """

    def __init__(self, *, err: bool = False) -> None:
        """Write to ``sys.stderr`` when *err* is set, else to ``sys.stdout``."""
        self._err = err

    def _target(self) -> TextIO:
        return sys.stderr if self._err else sys.stdout

    @property
    def encoding(self) -> str:
        """The target's encoding, UTF-8 when it names none."""
        return _stream_encoding(self._target())

    def write(self, s: str, /) -> int:
        """Write *s* to the target with what it cannot encode backslash-escaped; return ``len(s)``."""
        target = self._target()
        target.write(fit_text(s, target))
        return len(s)

    def flush(self) -> None:
        """Flush the target."""
        self._target().flush()

    def isatty(self) -> bool:
        """Whether the target is a terminal."""
        return self._target().isatty()

    def fileno(self) -> int:
        """The target's file descriptor (raises as the target does when it has none)."""
        return self._target().fileno()


def fitted_console_file(*, err: bool = False) -> IO[str]:
    """Return a :class:`FittedStream` typed as the ``IO[str]`` a Rich ``Console`` takes as its file.

    Rich declares ``file: IO[str]`` but reads only ``write`` and ``flush``, and ``encoding``,
    ``isatty`` and ``fileno`` through ``getattr`` (``console.py`` and ``_fileno.py``, read on rich 15.0.0),
    all of which the stream has; implementing the whole ``IO`` interface for that would be dead code.
    """
    return cast("IO[str]", FittedStream(err=err))
