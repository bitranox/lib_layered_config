"""Write command output in a form the target stream can always encode.

The fitting itself (JSON escapes, backslash escapes, why not force UTF-8) lives in
``adapters/_stream_text.py``, which ``display_config`` uses too, so the CLI and the display API write
the same text for the same stream.
"""

from __future__ import annotations

import re
import sys
from typing import Final

import rich_click as click

from ..adapters._stream_text import fit_json, fit_text

__all__ = ["emit_json", "emit_text", "escape_controls"]

# C0, DEL and C1: a newline or NEL starts a new line, an ESC starts a terminal sequence.
_CONTROL: Final = re.compile("[\x00-\x1f\x7f-\x9f]")


def escape_controls(text: str) -> str:
    r"""Return *text* with every control character written as a ``\uXXXX`` escape.

    For a key or path printed inside a line of human output: a newline in it would split the line,
    and on a terminal an ESC would start a sequence. A backslash is left as it is, so a Windows path
    reads unchanged (user decision 2026-11-16, R2-F3).

    Examples:
        >>> escape_controls("a\nb\x1b[31m\x85\x7f")
        'a\\u000ab\\u001b[31m\\u0085\\u007f'
        >>> escape_controls("C:\\ProgramData\\Acme")
        'C:\\ProgramData\\Acme'
    """
    return _CONTROL.sub(lambda match: f"\\u{ord(match.group()):04x}", text)


def emit_json(text: str) -> None:
    """Print JSON *text* to stdout, escaping what stdout cannot encode."""
    click.echo(fit_json(text, sys.stdout))


def emit_text(text: str, *, err: bool = False) -> None:
    """Print human *text* to stdout (stderr with *err*), backslash-escaping what it cannot encode."""
    click.echo(fit_text(text, sys.stderr if err else sys.stdout), err=err)
