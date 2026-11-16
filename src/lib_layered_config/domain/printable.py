"""Text that is safe to print inside one line of human output."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["escape_controls"]

# C0, DEL and C1: a newline or NEL starts a new line, an ESC starts a terminal sequence.
_CONTROL: Final = re.compile("[\x00-\x1f\x7f-\x9f]")


def escape_controls(text: str) -> str:
    r"""Return *text* with every control character written as a ``\uXXXX`` escape.

    For a key, path or refused value printed inside a line of human output: a newline in it would
    split the line, and on a terminal an ESC would start a sequence. A backslash is left as it is, so
    a Windows path reads unchanged (user decisions 2026-11-16, R2-F3 and R2-F4).

    Examples:
        >>> escape_controls("a\nb\x1b[31m\x85\x7f")
        'a\\u000ab\\u001b[31m\\u0085\\u007f'
        >>> escape_controls("C:\\ProgramData\\Acme")
        'C:\\ProgramData\\Acme'
    """
    return _CONTROL.sub(lambda match: f"\\u{ord(match.group()):04x}", text)
