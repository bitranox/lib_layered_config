"""Package exposing the lib_layered_config command-line interface."""

from __future__ import annotations

from typing import Callable, Iterable, Mapping, Optional, Sequence, cast

from importlib import metadata as _metadata

from pathlib import Path

import lib_cli_exit_tools
import rich_click as click

from ..core import default_env_prefix as _default_env_prefix  # backward compatibility import
from .common import (
    format_scalar,
    json_paths,
    load_distribution_metadata,
    normalise_examples_platform_option,
    normalise_platform_option,
    normalise_prefer,
    render_human,
    toggle_traceback,
    version_string,
)
from .constants import CLICK_CONTEXT_SETTINGS, TRACEBACK_SUMMARY, TRACEBACK_VERBOSE
from ..application.ports import SourceInfoPayload


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
def cli(traceback: bool) -> None:
    """Root command that remembers whether tracebacks should flow."""

    toggle_traceback(traceback)


def main(argv: Optional[Sequence[str]] = None, *, restore_traceback: bool = True) -> int:
    """Entry point that restores traceback preferences on exit."""

    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    previous_force_color = getattr(lib_cli_exit_tools.config, "traceback_force_color", False)
    try:
        try:
            run_cli = cast(Callable[..., int], lib_cli_exit_tools.run_cli)  # pyright: ignore[reportUnknownMemberType]
            return run_cli(cli, argv=list(argv) if argv is not None else None, prog_name="lib_layered_config")
        except BaseException as exc:  # noqa: BLE001
            print_exception = cast(Callable[..., None], lib_cli_exit_tools.print_exception_message)  # pyright: ignore[reportUnknownMemberType]
            print_exception(
                trace_back=lib_cli_exit_tools.config.traceback,
                length_limit=TRACEBACK_VERBOSE if lib_cli_exit_tools.config.traceback else TRACEBACK_SUMMARY,
            )
            exit_code_fn = cast(Callable[[BaseException], int], lib_cli_exit_tools.get_system_exit_code)  # pyright: ignore[reportUnknownMemberType]
            return exit_code_fn(exc)
    finally:
        if restore_traceback:
            lib_cli_exit_tools.config.traceback = previous_traceback
            lib_cli_exit_tools.config.traceback_force_color = previous_force_color


def _register_commands() -> None:
    from . import deploy, fail, generate, info, read

    for module in (read, deploy, generate, info, fail):
        module.register(cli)


_register_commands()

metadata = _metadata
_toggle_traceback = toggle_traceback
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


def _load_distribution_metadata() -> _metadata.PackageMetadata | None:
    """Wrapper that allows tests to monkeypatch metadata loading."""

    return load_distribution_metadata()


def _describe_distribution() -> tuple[str, ...]:
    """Yield human-readable metadata lines about the installed distribution."""

    meta = _load_distribution_metadata()
    if meta is None:
        return ("lib_layered_config (metadata unavailable)",)

    lines = [f"Info for {meta.get('Name', 'lib_layered_config')}:"]
    lines.append(f"  Version         : {meta.get('Version', version_string())}")
    lines.append(f"  Requires-Python : {meta.get('Requires-Python', '>=3.13')}")
    summary = meta.get("Summary")
    if summary:
        lines.append(f"  Summary         : {summary}")

    def _no_urls(_: str) -> Iterable[str] | None:
        return None

    get_all = cast(Callable[[str], Iterable[str] | None], getattr(meta, "get_all", _no_urls))
    for entry in get_all("Project-URL") or []:
        lines.append(f"  {entry}")
    return tuple(lines)


__all__ = [
    "cli",
    "main",
    "_default_env_prefix",
    "metadata",
    "_toggle_traceback",
    "_version_string",
    "_describe_distribution",
    "_load_distribution_metadata",
    "_normalise_platform",
    "_normalise_examples_platform",
    "_json_paths",
    "_render_human",
    "_format_scalar",
    "_normalise_prefer",
    "cli_read_config",
    "cli_read_config_json",
]
