"""The ``--json`` envelope: one JSON shape on stdout for every command, on success and on failure.

Each command keeps its default output; ``--json`` replaces it with one document::

    {"ok": true,  "command": "...", "data": ..., "skipped": [...]}
    {"ok": false, "command": "...", "error": {"type": "...", "message": "...", "exit_code": N}}

The exit code is the one the command would return without ``--json``, so a script can branch on it
whichever output it asked for.

Contents:
    * :func:`json_envelope_option` - the ``--json`` flag.
    * :func:`run_in_envelope` - run a command body and print its envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import rich_click as click
from lib_cli_exit_tools import CliSignalError, get_system_exit_code

from ..domain import json_codec
from .typed_click import option

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = [
    "json_envelope_option",
    "run_in_envelope",
]

_T = TypeVar("_T")

#: The ``--json`` flag, passed to the command as ``json_envelope``.
json_envelope_option = option(
    "--json",
    "json_envelope",
    is_flag=True,
    default=False,
    help="Print one JSON envelope {ok, command, data, skipped} instead, also when the command fails",
)


def run_in_envelope(
    command: str,
    produce: Callable[[], _T],
    *,
    skipped: Callable[[_T], Sequence[str]] | None = None,
) -> None:
    """Run *produce* and print its result as the ``--json`` envelope.

    Args:
        command: The command name the envelope reports.
        produce: The command body; returns the JSON-ready ``data``.
        skipped: Picks the skipped items out of ``data``; none when omitted.

    Raises:
        SystemExit: After printing the failure envelope, with the exit code the command would have
            returned without ``--json``.

    Examples:
        >>> from click.testing import CliRunner
        >>> @click.command()
        ... def demo() -> None:
        ...     run_in_envelope("demo", lambda: {"answer": 42})
        >>> print(CliRunner().invoke(demo).output.strip())
        {
          "ok": true,
          "command": "demo",
          "data": {
            "answer": 42
          },
          "skipped": []
        }
    """
    try:
        data = produce()
    except (click.Abort, CliSignalError):
        # An interrupt is not a command result: lib_cli_exit_tools maps it to the signal's exit code.
        raise
    except Exception as exc:
        code = _exit_code(exc)
        error = {"type": type(exc).__name__, "message": _message(exc), "exit_code": code}
        click.echo(json_codec.dumps({"ok": False, "command": command, "error": error}, indent=True))
        raise SystemExit(code) from exc
    left_out = list(skipped(data)) if skipped is not None else []
    click.echo(json_codec.dumps({"ok": True, "command": command, "data": data, "skipped": left_out}, indent=True))


def _exit_code(exc: Exception) -> int:
    """The exit code the command returns for *exc* without ``--json``.

    A Click exception carries its own (a usage error is 2); lib_cli_exit_tools maps everything else.
    """
    if isinstance(exc, click.ClickException):
        return exc.exit_code
    return get_system_exit_code(exc)


def _message(exc: Exception) -> str:
    """The message the command prints for *exc*; a Click exception keeps its own wording."""
    if isinstance(exc, click.ClickException):
        return exc.format_message()
    return str(exc)
