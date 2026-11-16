"""Write command output in a form the target stream can always encode.

The fitting itself (JSON escapes, backslash escapes, why not force UTF-8) lives in
``adapters/_stream_text.py``, which ``display_config`` uses too, so the CLI and the display API write
the same text for the same stream.
"""

from __future__ import annotations

import sys

import rich_click as click

from ..adapters._stream_text import fit_json, fit_text

__all__ = ["emit_json", "emit_text"]


def emit_json(text: str) -> None:
    """Print JSON *text* to stdout, escaping what stdout cannot encode."""
    click.echo(fit_json(text, sys.stdout))


def emit_text(text: str, *, err: bool = False) -> None:
    """Print human *text* to stdout (stderr with *err*), backslash-escaping what it cannot encode."""
    click.echo(fit_text(text, sys.stderr if err else sys.stdout), err=err)
