"""The ``--json`` envelope: one JSON shape on stdout for every command, on success and on failure.

Each command keeps its default output; ``--json`` replaces it with one document::

    {"ok": true,  "command": "...", "data": ..., "skipped": [...]}
    {"ok": false, "command": "...", "error": {"type": "...", "message": "...", "exit_code": N}}

The exit code is the one the command would return without ``--json``, so a script can branch on it
whichever output it asked for.

Contents:
    * :data:`json_envelope_option` - the ``--json`` flag.
    * :class:`EnvelopeCommand` - the command class that prints the failure envelope for a usage error
      Click raises while parsing, before the command body runs.
    * :func:`run_in_envelope` - run a command body and print its envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import rich_click as click
from lib_cli_exit_tools import CliSignalError, get_system_exit_code

from ..domain import json_codec
from .output import emit_json
from .typed_click import option

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

__all__ = [
    "EnvelopeCommand",
    "json_envelope_option",
    "run_in_envelope",
]

_T = TypeVar("_T")

_JSON_FLAG = "--json"

#: The ``--json`` flag, passed to the command as ``json_envelope``.
json_envelope_option = option(
    _JSON_FLAG,
    "json_envelope",
    is_flag=True,
    default=False,
    help="Print one JSON envelope {ok, command, data, skipped} instead; on failure {ok, command, error}",
)


def run_in_envelope(
    command: str,
    produce: Callable[[], _T],
    *,
    skipped: Callable[[_T], Sequence[str]] | None = None,
    detail: Callable[[Exception], Mapping[str, object]] | None = None,
) -> None:
    """Run *produce* and print its result as the ``--json`` envelope.

    Args:
        command: The command name the envelope reports.
        produce: The command body; returns the JSON-ready ``data``.
        skipped: Picks the skipped items out of ``data``; none when omitted.
        detail: Extra fields for the failure envelope's ``error`` object, read from the exception
            (deploy's ``written``); its ``type``, ``message`` and ``exit_code`` always win.

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
        left_out = list(skipped(data)) if skipped is not None else []
        # Written inside the try: the envelope puts data one level below its top, so a config as deep
        # as the command's plain JSON output can write is too deep here, and that refusal must print
        # the failure envelope like any other.
        text = json_codec.dumps({"ok": True, "command": command, "data": data, "skipped": left_out}, indent=True)
    except (click.Abort, CliSignalError):
        # An interrupt is not a command result: lib_cli_exit_tools maps it to the signal's exit code.
        raise
    except Exception as exc:
        raise SystemExit(_print_failure(command, exc, detail=detail)) from exc
    emit_json(text)


class EnvelopeCommand(click.RichCommand):
    """A command whose parse errors print the ``--json`` failure envelope.

    A missing required option, a bad value or an unknown option is raised while Click parses the
    arguments, before the command body (and :func:`run_in_envelope`) runs. When ``--json`` is among
    the command's own arguments, this prints the failure envelope for it and exits with Click's
    code (2); without ``--json`` Click's usage text is unchanged. ``--json`` is found by text before
    parsing, so an option value spelled ``--json`` counts too. An unknown subcommand fails in the
    group and never reaches a command, so it keeps Click's text.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Parse *args*, printing the failure envelope on a usage error when ``--json`` was given."""
        # Read before parsing: Click consumes the list it is handed.
        wants_envelope = _JSON_FLAG in args
        try:
            return super().parse_args(ctx, args)
        except click.ClickException as exc:
            if not wants_envelope:
                raise
            raise SystemExit(_print_failure(self.name or ctx.info_name or "", exc)) from exc


def _print_failure(
    command: str, exc: Exception, *, detail: Callable[[Exception], Mapping[str, object]] | None = None
) -> int:
    """Print the failure envelope for *exc*, with *detail*'s fields, and return the exit code it reports."""
    code = _exit_code(exc)
    error: dict[str, object] = dict(detail(exc)) if detail is not None else {}
    error.update({"type": type(exc).__name__, "message": _message(exc), "exit_code": code})
    emit_json(json_codec.dumps({"ok": False, "command": command, "error": error}, indent=True))
    return code


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
