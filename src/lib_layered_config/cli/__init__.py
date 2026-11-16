"""Package exposing the lib_layered_config command-line interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import lib_cli_exit_tools
import rich_click as click
from lib_cli_exit_tools import cli_session

from . import deploy, fail, generate, info, read
from .common import version_string
from .constants import CLICK_CONTEXT_SETTINGS, TRACEBACK_SUMMARY, TRACEBACK_VERBOSE
from .read import read_command as cli_read_config
from .read import read_json_command as cli_read_config_json
from .stderr_warnings import attach_stderr_warnings
from .typed_click import current_context, option, version_option

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


@click.group(
    help="Immutable layered configuration reader",
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@version_option(
    version=version_string(),
    prog_name="lib_layered_config",
    message="lib_layered_config version %(version)s",
)
@option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
def cli(*, traceback: bool) -> None:
    """Root command for the CLI group: library warnings go to stderr until the command ends.

    The ``--traceback`` choice is written into ``lib_cli_exit_tools.config`` here, first, because the
    session's error handler reads it when it reports an exception. Reading it from ``argv`` in
    ``main()`` instead missed every console-script run, which passes no ``argv``; ``cli_session``
    restores the whole config when the call ends.
    """
    lib_cli_exit_tools.config.traceback = traceback
    lib_cli_exit_tools.config.traceback_force_color = traceback
    current_context().call_on_close(attach_stderr_warnings())


def main(argv: Sequence[str] | None = None, *, restore_traceback: bool = True) -> int:
    """Entry point wiring the CLI through ``lib_cli_exit_tools.cli_session``."""
    args_list = list(argv) if argv is not None else None

    with cli_session(
        summary_limit=TRACEBACK_SUMMARY,
        verbose_limit=TRACEBACK_VERBOSE,
        restore=restore_traceback,
    ) as run:
        runner = cast("Callable[..., int]", run)
        return runner(
            cli,
            argv=args_list,
            prog_name="lib_layered_config",
        )


def _register_commands() -> None:
    for module in (read, deploy, generate, info, fail):
        module.register(cli)


_register_commands()


__all__ = [
    "cli",
    "cli_read_config",
    "cli_read_config_json",
    "main",
]
