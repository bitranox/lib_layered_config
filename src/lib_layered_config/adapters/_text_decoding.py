"""Decode configuration bytes as UTF-8, failing with the library's own error.

The error names the file, the line and the byte offset, and never the content: it is raised
outside the ``except`` block, so no ``UnicodeDecodeError`` (whose ``.object`` holds the whole
file) stays reachable through ``__context__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.errors import InvalidFormatError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["decode_utf8"]


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
