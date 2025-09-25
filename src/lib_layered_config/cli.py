"""CLI adapter wiring the domain stubs into a Click-powered interface.

Purpose
-------
Expose a stable command-line surface so tooling, documentation, and packaging
automation can be exercised while the richer logging helpers are being built.
By keeping the CLI thin and delegating behavior to
``lib_layered_config.lib_layered_config`` the transport stays aligned
with the Clean Architecture boundaries referenced in
``docs/systemdesign/module_reference.md``.

Contents
--------
* :data:`CLICK_CONTEXT_SETTINGS` – shared Click settings ensuring consistent
  ``--help`` behavior across commands.
* :func:`cli` – root command group that applies global options and syncs the
  ``lib_cli_exit_tools`` configuration.
* :func:`cli_main` – fallback invoked when no subcommand is provided; calls
  the domain placeholder ``main`` helper.
* :func:`cli_info`, :func:`cli_hello`, :func:`cli_fail` – subcommands covering
  metadata printing, success path, and failure path.
* :func:`main` – composition helper that defers to ``lib_cli_exit_tools`` for
  exit-code normalization while restoring the global traceback preference.

System Role
-----------
The CLI is the primary adapter for local development workflows; packaging
targets register the console script defined in :mod:`lib_layered_config.__init__conf__`.
Other transports (HTTP/TUI) can remain consistent by reusing the same domain
helpers documented here.
"""

from __future__ import annotations

from typing import Optional, Sequence

import click

import lib_cli_exit_tools

from . import __init__conf__
from .lib_layered_config import hello_world as _hello_world
from .lib_layered_config import i_should_fail as _fail
from .lib_layered_config import main as _domain_main

# Maintain a single help option map so every command advertises ``-h`` and
# ``--help`` consistently; Click's default only exposes ``--help``.
CLICK_CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])  # noqa: C408


@click.group(
    help=__init__conf__.title,
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.version_option(
    version=__init__conf__.version,
    prog_name=__init__conf__.shell_command,
    message=f"{__init__conf__.shell_command} version {__init__conf__.version}",
)
@click.option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
@click.pass_context
def cli(ctx: click.Context, traceback: bool) -> None:
    """Root command storing global flags and syncing shared traceback state.

    Why
        The CLI must provide a switch for verbose tracebacks so developers can
        toggle diagnostic depth without editing configuration files.

    What
        Ensures a dict-based context, stores the ``traceback`` flag, and mirrors
        the value into ``lib_cli_exit_tools.config.traceback`` so downstream
        helpers observe the preference. When no subcommand is requested the
        function delegates to :func:`cli_main` to exercise the sanctioned
        default behavior.

    Side Effects
        Mutates :mod:`lib_cli_exit_tools.config` to reflect the requested
        traceback mode.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> result = runner.invoke(cli, ["hello"])
    >>> result.exit_code
    0
    >>> "Hello World" in result.output
    True
    """

    ctx.ensure_object(dict)
    ctx.obj["traceback"] = traceback
    lib_cli_exit_tools.config.traceback = traceback
    if ctx.invoked_subcommand is None:
        cli_main()
        return None


def cli_main() -> None:
    """Run the domain placeholder when the CLI is invoked without a command.

    Why
        Some automation scripts and shell users expect bare invocations to
        perform a sensible default action. While the domain layer currently
        exposes only a no-op `main`, calling it here establishes the contract
        and keeps future extensions discoverable.

    What
        Delegates to :func:`lib_layered_config.lib_layered_config.main`
        so the sanctioned entry point is exercised even when no subcommand is
        chosen. The helper returns ``None`` and produces no output today.

    Side Effects
        None. The domain placeholder intentionally avoids I/O to keep imports
        deterministic.

    Examples
    --------
    >>> cli_main()

    """

    _domain_main()


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print resolved metadata so users can inspect installation details.

    Why
        Surface the distribution metadata that installers use (name, version,
        homepage, etc.) without requiring developers to inspect the
        ``pyproject.toml`` or package metadata manually.

    What
        Delegates to :func:`lib_layered_config.__init__conf__.print_info`
        which formats the metadata block.

    Side Effects
        Writes to ``stdout``.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> info_result = runner.invoke(cli, ["info"])
    >>> info_result.exit_code
    0
    >>> info_result.output.splitlines()[0]
    'Info for lib_layered_config:'
    """

    __init__conf__.print_info()


@cli.command("hello", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_hello() -> None:
    """Demonstrate the success path by calling the shared greeting helper.

    Why
        Provides a trivial success scenario so CLI smoke tests and onboarding
        docs can verify the scaffold quickly.

    What
        Calls :func:`lib_layered_config.lib_layered_config.hello_world`.

    Side Effects
        Writes the greeting to ``stdout`` via the helper.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> hello_result = runner.invoke(cli, ["hello"])
    >>> hello_result.output.strip()
    'Hello World'
    """

    _hello_world()


@cli.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Trigger the intentional failure helper to test error handling.

    Why
        Ensures the CLI can propagate and format errors consistently,
        especially when users toggle ``--traceback``.

    What
        Calls :func:`lib_layered_config.lib_layered_config.i_should_fail`
        which always raises ``RuntimeError``.

    Side Effects
        Raises ``RuntimeError``.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> fail_result = runner.invoke(cli, ["fail"])
    >>> fail_result.exit_code != 0
    True
    >>> isinstance(fail_result.exception, RuntimeError)
    True
    """

    _fail()


def main(argv: Optional[Sequence[str]] = None, *, restore_traceback: bool = True) -> int:
    """Execute the CLI with shared exit handling and return the exit code.

    Why
        The project standardizes exit behavior through ``lib_cli_exit_tools`` so
        all CLI entry points behave the same in CI and local shells.

    What
        Delegates to :func:`lib_cli_exit_tools.run_cli`, optionally restoring the
        previous global traceback preference once execution completes.

    Parameters
    ----------
    argv:
        Optional argument vector. ``None`` means defer to ``sys.argv``.
    restore_traceback:
        Whether to reset :mod:`lib_cli_exit_tools.config.traceback` after the
        CLI finishes. Defaults to ``True`` so subsequent invocations observe the
        pre-existing configuration.

    Returns
    -------
    int
        Exit code produced by ``run_cli``.

    Side Effects
        Mutates ``lib_cli_exit_tools.config.traceback`` while the CLI runs and
        optionally restores it afterwards.

    Examples
    --------
    >>> main(["hello"])
    Hello World
    0
    """

    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    try:
        return lib_cli_exit_tools.run_cli(
            cli,
            argv=list(argv) if argv is not None else None,
            prog_name=__init__conf__.shell_command,
        )
    finally:
        if restore_traceback:
            lib_cli_exit_tools.config.traceback = previous_traceback
