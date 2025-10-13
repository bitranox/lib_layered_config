"""Package exposing the lib_layered_config command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence, cast

import rich_click as click
from lib_cli_exit_tools import cli_session

from ..application.ports import SourceInfoPayload
from .common import (
    describe_distribution,
    format_scalar,
    json_paths,
    normalise_examples_platform_option,
    normalise_platform_option,
    normalise_prefer,
    render_human,
    version_string,
)
from .constants import CLICK_CONTEXT_SETTINGS, TRACEBACK_SUMMARY, TRACEBACK_VERBOSE
from .read import read_command as cli_read_config, read_json_command as cli_read_config_json


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


def main(argv: Optional[Sequence[str]] = None, *, restore_traceback: bool = True) -> int:
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

_version_string = version_string


def _normalise_platform(value: str | None) -> str | None:  # pyright: ignore[reportUnusedFunction]
    return normalise_platform_option(value)


def _normalise_examples_platform(value: str | None) -> str | None:  # pyright: ignore[reportUnusedFunction]
    return normalise_examples_platform_option(value)


def _json_paths(paths: Iterable[Path]) -> str:  # pyright: ignore[reportUnusedFunction]
    return json_paths(paths)


def _render_human(data: Mapping[str, object], provenance: Mapping[str, SourceInfoPayload]) -> str:  # pyright: ignore[reportUnusedFunction]
    return render_human(data, provenance)


def _format_scalar(value: object) -> str:  # pyright: ignore[reportUnusedFunction]
    return format_scalar(value)


def _normalise_prefer(values: Sequence[str]) -> tuple[str, ...] | None:  # pyright: ignore[reportUnusedFunction]
    return normalise_prefer(values)


def _describe_distribution() -> tuple[str, ...]:
    """Expose CLI metadata lines for backwards-compatible tests."""

    return tuple(describe_distribution())


__all__ = [
    "cli",
    "main",
    "_version_string",
    "_describe_distribution",
    "_normalise_platform",
    "_normalise_examples_platform",
    "_json_paths",
    "_render_human",
    "_format_scalar",
    "_normalise_prefer",
    "cli_read_config",
    "cli_read_config_json",
]
