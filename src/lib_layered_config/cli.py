"""CLI adapter for ``lib_layered_config`` built on ``lib_cli_exit_tools``.

Purpose
-------
Expose the layered configuration reader via a first-class command line
interface so operators can inspect precedence outcomes without writing Python
code. The CLI mirrors the methodology used in ``bitranox_template_py_cli`` while
adapting the commands to the configuration domain (``read-config``,
``env-prefix``, etc.).

Contents
--------
* :data:`CLICK_CONTEXT_SETTINGS` – shared Click settings ensuring ``-h`` works.
* :func:`cli` – root command that wires global traceback handling into
  ``lib_cli_exit_tools``.
* :func:`cli_info` – prints distribution metadata for quick diagnostics.
* :func:`cli_env_prefix` – helper exposing :func:`lib_layered_config.core.default_env_prefix`.
* :func:`cli_read_config` – calls :func:`lib_layered_config.core.read_config` and
  formats the result as JSON (optionally with provenance).
* :func:`cli_deploy_config` – copies configuration artifacts into layered directories.
* :func:`cli_generate_examples` – scaffolds example configuration trees.
* :func:`main` – entry point used by ``console_scripts`` registration.

System Role
-----------
The CLI lives in the outermost layer of the Clean Architecture stack. It
invokes the composition root (``read_config``) and never reaches into adapter
implementation details directly. ``lib_cli_exit_tools`` centralises the exit code
strategy so all commands behave consistently across shells and CI.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Final, Optional, Sequence

import lib_cli_exit_tools
import rich_click as click

from .core import default_env_prefix as _default_env_prefix
from .core import read_config, read_config_raw
from .examples import deploy_config as _deploy_config
from .examples import generate_examples as _generate_examples
from .testing import i_should_fail

CLICK_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
_TRACEBACK_SUMMARY_LIMIT: Final[int] = 500
_TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000

TARGET_CHOICES: Final[tuple[str, ...]] = ("app", "host", "user")
EXAMPLE_PLATFORM_CHOICES: Final[tuple[str, ...]] = ("posix", "windows")


def _resolve_version() -> str:
    """Return the installed package version with sensible fallbacks.

    Why
        ``click.version_option`` requires a string at decoration time. Fetching
        metadata lazily avoids hard-coding the version and keeps editable installs
        working without additional wiring.

    Returns
    -------
    str
        Distribution version if available, otherwise ``"0.0.0"``.
    """

    try:
        return metadata.version("lib_layered_config")
    except metadata.PackageNotFoundError:
        return "0.0.0"


@click.group(
    help="Immutable layered configuration reader",
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@click.version_option(
    version=_resolve_version(),
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
    """Root command configuring traceback handling for all subcommands.

    Why
        Downstream helpers (``lib_cli_exit_tools`` and command handlers) need the
        traceback preference so they can render either summary tracebacks or the
        full stack when debugging.

    What
        Ensures the Click context exists, stores the preference, and mirrors it
        into :mod:`lib_cli_exit_tools.config` which the shared ``main`` helper
        reads when formatting exceptions.

    Side Effects
        Mutates ``lib_cli_exit_tools.config.traceback`` and
        ``lib_cli_exit_tools.config.traceback_force_color``.
    """

    ctx.ensure_object(dict)
    ctx.obj["traceback"] = traceback
    lib_cli_exit_tools.config.traceback = traceback
    lib_cli_exit_tools.config.traceback_force_color = traceback


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print basic distribution metadata so users can confirm installation."""

    try:
        meta = metadata.metadata("lib_layered_config")
    except metadata.PackageNotFoundError:
        click.echo("lib_layered_config (metadata unavailable)")
        return
    click.echo(f"Info for {meta.get('Name', 'lib_layered_config')}:")
    click.echo(f"  Version         : {meta.get('Version', _resolve_version())}")
    click.echo(f"  Requires-Python : {meta.get('Requires-Python', '>=3.10')}")
    summary = meta.get("Summary")
    if summary:
        click.echo(f"  Summary         : {summary}")
    for entry in meta.get_all("Project-URL") or []:
        click.echo(f"  {entry}")


@cli.command("env-prefix", context_settings=CLICK_CONTEXT_SETTINGS)
@click.argument("slug")
def cli_env_prefix(slug: str) -> None:
    """Compute the canonical environment prefix for *slug*.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> result = runner.invoke(cli, ["env-prefix", "config-kit"])
    >>> result.output.strip()
    'CONFIG_KIT'
    """

    click.echo(_default_env_prefix(slug))


@cli.command("deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--source",
    "source",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    required=True,
    help="Path to the configuration file that should be copied",
)
@click.option("--vendor", required=True, help="Vendor namespace (e.g. organisation name)")
@click.option("--app", required=True, help="Application name used for host/user directories")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option(
    "--target",
    "targets",
    multiple=True,
    required=True,
    type=click.Choice(TARGET_CHOICES, case_sensitive=False),
    help="Layer targets to deploy to (repeatable)",
)
@click.option(
    "--platform",
    default=None,
    help="Override auto-detected platform (e.g. linux, darwin, windows)",
)
@click.option(
    "--force/--no-force",
    default=False,
    help="Overwrite existing files at the destination if set",
    show_default=True,
)
def cli_deploy_config(
    source: Path,
    vendor: str,
    app: str,
    slug: str,
    targets: Sequence[str],
    platform: Optional[str],
    force: bool,
) -> None:
    """Copy *source* into the requested configuration layers.

    Why
    ----
    Provide a CLI entrypoint for :func:`lib_layered_config.examples.deploy.deploy_config`
    so operators can scaffold layered directories without writing Python.

    What
    -----
    Emits a JSON array listing the files that were created or overwritten.
    Pass ``--force`` to override existing files in place.
    """

    normalized_targets = _normalize_targets(targets)
    normalized_platform = _normalize_platform(platform)
    created = _deploy_config(
        source,
        vendor=vendor,
        app=app,
        targets=normalized_targets,
        slug=slug,
        platform=normalized_platform,
        force=force,
    )
    click.echo(json.dumps([str(path) for path in created], indent=2))


@cli.command("generate-examples", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--destination",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, resolve_path=True),
    required=True,
    help="Directory that will receive the example tree",
)
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option("--vendor", required=True, help="Vendor namespace used in examples")
@click.option("--app", required=True, help="Application name used in examples")
@click.option(
    "--platform",
    default=None,
    help="Override platform layout (posix/windows)",
)
@click.option(
    "--force/--no-force",
    default=False,
    help="Overwrite existing example files if set",
    show_default=True,
)
def cli_generate_examples(
    destination: Path,
    slug: str,
    vendor: str,
    app: str,
    platform: Optional[str],
    force: bool,
) -> None:
    """Generate canonical example configuration files under *destination*."""

    normalized_platform = _normalize_examples_platform(platform)
    created = _generate_examples(
        destination,
        slug=slug,
        vendor=vendor,
        app=app,
        force=force,
        platform=normalized_platform,
    )
    click.echo(json.dumps([str(path) for path in created], indent=2))


@cli.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Trigger a deterministic error for testing traceback handling.

    This mirrors the helper exposed by `lib_layered_config.testing.i_should_fail`.
    """

    i_should_fail()


@cli.command("read", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True, help="Vendor namespace (e.g. organisation name)")
@click.option("--app", required=True, help="Application name used for host/user directories")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option(
    "--prefer",
    multiple=True,
    help="Preferred file suffix ordering for config.d entries (repeatable)",
)
@click.option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
    help="Starting directory for .env upward search (defaults to CWD)",
)
@click.option(
    "--indent",
    type=int,
    default=None,
    help="Pretty-print JSON output with the provided indent size",
)
@click.option(
    "--provenance/--no-provenance",
    default=False,
    help="Include provenance metadata for each key in the output",
)
def cli_read_config(
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str],
    start_dir: Optional[Path],
    indent: Optional[int],
    provenance: bool,
) -> None:
    """Load layered configuration and print the result as JSON.

    Parameters mirror :func:`lib_layered_config.core.read_config`. Repeating
    ``--prefer`` adjusts the ordering used inside ``config.d`` directories. When
    ``--provenance`` is supplied the output includes merge metadata for each key.
    """

    prefer_order = _normalize_prefer(prefer)
    start_dir_str = str(start_dir) if start_dir is not None else None
    if provenance:
        data, meta = read_config_raw(
            vendor=vendor,
            app=app,
            slug=slug,
            prefer=prefer_order,
            start_dir=start_dir_str,
        )
        payload = {"config": data, "provenance": meta}
        click.echo(json.dumps(payload, indent=indent, separators=(",", ":")))
        return

    config = read_config(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=prefer_order,
        start_dir=start_dir_str,
    )
    click.echo(config.to_json(indent=indent))


def _normalize_prefer(values: Sequence[str]) -> Optional[Sequence[str]]:
    """Normalise preferred suffixes to lowercase tuples without leading dots."""

    if not values:
        return None
    return tuple(value.lower().lstrip(".") for value in values)


def _normalize_targets(values: Sequence[str]) -> tuple[str, ...]:
    """Return CLI target choices normalised to lowercase while preserving order."""

    return tuple(value.lower() for value in values)


def _normalize_examples_platform(platform: Optional[str]) -> Optional[str]:
    """Return a generate_examples-compatible platform identifier or ``None``."""

    if platform is None:
        return None
    alias = platform.strip().lower()
    if not alias:
        return None
    mapping = {
        "posix": "posix",
        "linux": "posix",
        "darwin": "posix",
        "mac": "posix",
        "macos": "posix",
        "windows": "windows",
        "win": "windows",
        "win32": "windows",
        "wine": "windows",
    }
    try:
        return mapping[alias]
    except KeyError as exc:
        raise click.BadParameter(
            "Platform must be one of: posix, linux, darwin, mac, macos, windows, win, win32, wine.",
            param_hint="--platform",
        ) from exc


def _normalize_platform(platform: Optional[str]) -> Optional[str]:
    """Return a resolver-friendly platform identifier or ``None``."""

    if platform is None:
        return None
    alias = platform.strip().lower()
    if not alias:
        return None
    mapping = {
        "linux": "linux",
        "posix": "linux",
        "darwin": "darwin",
        "mac": "darwin",
        "macos": "darwin",
        "win": "win32",
        "win32": "win32",
        "windows": "win32",
        "wine": "win32",
    }
    try:
        return mapping[alias]
    except KeyError as exc:
        raise click.BadParameter(
            "Platform must be one of: linux, posix, darwin, mac, macos, win, win32, windows, wine.",
            param_hint="--platform",
        ) from exc


def main(argv: Optional[Sequence[str]] = None, *, restore_traceback: bool = True) -> int:
    """Execute the CLI with shared exit handling and return the exit code."""

    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    previous_force_color = getattr(lib_cli_exit_tools.config, "traceback_force_color", False)
    try:
        try:
            return lib_cli_exit_tools.run_cli(
                cli,
                argv=list(argv) if argv is not None else None,
                prog_name="lib_layered_config",
            )
        except BaseException as exc:  # noqa: BLE001 - funnel through shared printers
            lib_cli_exit_tools.print_exception_message(
                trace_back=lib_cli_exit_tools.config.traceback,
                length_limit=(
                    _TRACEBACK_VERBOSE_LIMIT if lib_cli_exit_tools.config.traceback else _TRACEBACK_SUMMARY_LIMIT
                ),
            )
            return lib_cli_exit_tools.get_system_exit_code(exc)
    finally:
        if restore_traceback:
            lib_cli_exit_tools.config.traceback = previous_traceback
            lib_cli_exit_tools.config.traceback_force_color = previous_force_color


if __name__ == "__main__":  # pragma: no cover - exercised via console entry point
    raise SystemExit(main(sys.argv[1:]))
