"""Package exposing the lib_layered_config command-line interface."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

import rich_click as click
from lib_cli_exit_tools import cli_session

from .common import version_string
from .constants import CLICK_CONTEXT_SETTINGS, TRACEBACK_SUMMARY, TRACEBACK_VERBOSE
from .read import read_command as cli_read_config
from .read import read_json_command as cli_read_config_json


@click.group(
    help="Immutable layered configuration reader",
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@click.version_option(
    version=version_string(),
    prog_name="lib_layered_config",
    message="lib_layered_config version %(version)s",
)
@click.option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
@click.pass_context
def cli(ctx: click.Context, traceback: bool) -> None:
    """Root command storing the requested traceback preference."""
    ctx.ensure_object(dict)
    ctx.obj["traceback"] = traceback


def main(argv: Sequence[str] | None = None, *, restore_traceback: bool = True) -> int:
    """Entry point wiring the CLI through ``lib_cli_exit_tools.cli_session``."""
    args_list = list(argv) if argv is not None else None
    overrides = _session_overrides(args_list)

    with cli_session(
        summary_limit=TRACEBACK_SUMMARY,
        verbose_limit=TRACEBACK_VERBOSE,
        overrides=overrides or None,
        restore=restore_traceback,
    ) as run:
        runner = cast("Callable[..., int]", run)
        return runner(
            cli,
            argv=args_list,
            prog_name="lib_layered_config",
        )


def _session_overrides(argv: Sequence[str] | None) -> dict[str, object]:
    """Derive configuration overrides for ``cli_session`` based on CLI args."""
    if not argv:
        return {}

    try:
        ctx = cli.make_context("lib_layered_config", list(argv), resilient_parsing=True)
    except click.ClickException:
        return {}

    try:
        enabled = bool(ctx.params.get("traceback", False))
    finally:
        ctx.close()

    return {"traceback": enabled} if enabled else {}


def _register_commands() -> None:
    from . import deploy, fail, generate, info, read

    for module in (read, deploy, generate, info, fail):
        module.register(cli)


_register_commands()


__all__ = [
    "cli",
    "main",
    "cli_read_config",
    "cli_read_config_json",
]
