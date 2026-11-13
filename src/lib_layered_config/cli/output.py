r"""Write command output in a form the target stream can always encode.

A piped stdout on Windows uses the ANSI code page (cp1252 on a German or English install), which has
no CJK characters and no emoji, so printing such a configuration value raised
``UnicodeEncodeError`` and the command exited with nothing on stdout, a ``--json`` envelope
included. Output is therefore fitted to the stream's own encoding before it is written:

- JSON text writes each character the stream cannot encode as a ``\uXXXX`` escape (a surrogate pair
  above U+FFFF). Non-ASCII characters in JSON text occur only inside strings, so the result is valid
  JSON that parses back to the same value.
- Human text writes each such character as a Python backslash escape (``errors="backslashreplace"``).

A character the stream can encode is written as it is, so a UTF-8 stream, and a cp1252 stream
printing umlauts, get exactly the text they got before. Forcing UTF-8 instead was rejected: it
would turn umlauts a cp1252 console shows correctly today into mojibake.

The JSON escape runs as a registered codec error handler, so the common path stays inside the codec
rather than a per-character Python loop.
"""

from __future__ import annotations

import codecs
import sys

import rich_click as click

__all__ = ["emit_json", "emit_text"]

_JSON_ESCAPE = "lib_layered_config.json_escape"
# The highest code point a single JSON \u escape can carry; above it, a surrogate pair.
_BMP_MAX = 0xFFFF


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


def _stream_encoding(*, err: bool) -> str:
    """Return the encoding of stdout (or stderr with *err*), UTF-8 when the stream names none."""
    encoding: object = getattr(sys.stderr if err else sys.stdout, "encoding", None)
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


def emit_json(text: str) -> None:
    """Print JSON *text* to stdout, escaping what stdout cannot encode."""
    click.echo(_fit_to_encoding(text, _stream_encoding(err=False), errors=_JSON_ESCAPE))


def emit_text(text: str, *, err: bool = False) -> None:
    """Print human *text* to stdout (stderr with *err*), backslash-escaping what it cannot encode."""
    click.echo(_fit_to_encoding(text, _stream_encoding(err=err), errors="backslashreplace"), err=err)
