"""Decode configuration bytes as UTF-8, failing with the library's own error.

The error names the file, the line and the byte offset, and never the content: it is raised
outside the ``except`` block, so no ``UnicodeDecodeError`` (whose ``.object`` holds the whole
file) stays reachable through ``__context__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from ..domain.errors import InvalidFormatError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["decode_utf8", "decode_yaml_text"]

#: Checked before the UTF-16 BOMs: the UTF-32 LE BOM starts with the UTF-16 LE BOM, so
#: checking UTF-16 first would misdetect a UTF-32 LE file as UTF-16.
_UTF32_LE_BOM: Final[bytes] = b"\xff\xfe\x00\x00"
_UTF32_BE_BOM: Final[bytes] = b"\x00\x00\xfe\xff"
_UTF16_LE_BOM: Final[bytes] = b"\xff\xfe"
_UTF16_BE_BOM: Final[bytes] = b"\xfe\xff"


def decode_utf8(raw: bytes, *, path: str | Path) -> str:
    """Return *raw* decoded as UTF-8.

    Raises:
        InvalidFormatError: *raw* is not valid UTF-8.

    Examples:
        >>> decode_utf8(b"a = 1", path="x.toml")
        'a = 1'
        >>> try:
        ...     decode_utf8(b"a\\n\\xff", path="x.env")
        ... except InvalidFormatError as exc:
        ...     print(exc)
        x.env is not valid UTF-8 (line 2, byte offset 2)
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        offset = exc.start
    line = raw.count(b"\n", 0, offset) + 1
    raise InvalidFormatError(f"{path} is not valid UTF-8 (line {line}, byte offset {offset})")


def decode_yaml_text(raw: bytes, *, path: str | Path) -> str:
    """Return *raw* decoded as YAML source text, honoring a UTF-16/UTF-32 BOM.

    PyYAML's own reader detects a UTF-16 byte-order mark and decodes accordingly (a YAML file
    saved by PowerShell 5 ``Out-File`` or Notepad "Unicode" carries one); this module's own BOM
    check extends that to UTF-32, which PyYAML's reader does not detect on its own. Every other
    YAML file, like every TOML/JSON/.env file, stays strict UTF-8 (a UTF-8 BOM keeps working as
    before, via :func:`decode_utf8`).

    Args:
        raw: Raw file bytes.
        path: Source path used to build the error message.

    Returns:
        The decoded text.

    Raises:
        InvalidFormatError: *raw* starts with a UTF-16/UTF-32 BOM but its bytes do not decode
            under that encoding, or *raw* has no such BOM and is not valid UTF-8.

    Examples:
        >>> decode_yaml_text(b"k: 1\\n", path="x.yaml")
        'k: 1\\n'
        >>> decode_yaml_text("k: 1\\n".encode("utf-16"), path="x.yaml")
        'k: 1\\n'
        >>> try:
        ...     decode_yaml_text(b"\\xff\\xfe\\x00", path="x.yaml")
        ... except InvalidFormatError as exc:
        ...     print(exc)
        x.yaml is not valid UTF-16 (byte offset 2)
    """
    if raw.startswith(_UTF32_LE_BOM) or raw.startswith(_UTF32_BE_BOM):
        return _decode_bom(raw, "utf-32", "UTF-32", path=path)
    if raw.startswith(_UTF16_LE_BOM) or raw.startswith(_UTF16_BE_BOM):
        return _decode_bom(raw, "utf-16", "UTF-16", path=path)
    return decode_utf8(raw, path=path)


def _decode_bom(raw: bytes, codec: str, label: str, *, path: str | Path) -> str:
    """Decode *raw* with *codec* (a BOM-aware generic codec name), or raise content-free.

    Args:
        raw: Raw file bytes, starting with the BOM that selected *codec*.
        codec: Python codec name (``"utf-16"`` or ``"utf-32"``); the generic form strips the
            BOM and picks the byte order from it.
        label: Human-readable encoding name for the error message (``"UTF-16"``/``"UTF-32"``).
        path: Source path used to build the error message.

    Returns:
        The decoded text.

    Raises:
        InvalidFormatError: *raw* does not decode under *codec*.
    """
    try:
        return raw.decode(codec)
    except UnicodeDecodeError as exc:
        offset = exc.start
    raise InvalidFormatError(f"{path} is not valid {label} (byte offset {offset})")
