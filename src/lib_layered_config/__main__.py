"""Module entry point ensuring SystemExit semantics match project standards.

Purpose
-------
Provide the ``python -m lib_layered_config`` path mandated by the
project's packaging guidelines. The wrapper mirrors the error handling performed
by :func:`lib_cli_exit_tools.run_cli` so that module execution remains
consistent with calling :func:`lib_layered_config.cli.main` directly.

System Role
-----------
This module lives in the adapters layer. It bridges CPython's module execution
entry point to the shared CLI helper while preserving the previous traceback
preference if an exception occurs, as captured in
``docs/systemdesign/module_reference.md``.
"""

from __future__ import annotations

from typing import Final

import lib_cli_exit_tools

from . import cli

# Match lib_cli_exit_tools defaults (500 chars) so truncated tracebacks mirror
# the console script behaviour documented in docs/systemdesign/module_reference.
_TRUNCATED_TRACEBACK_LIMIT: Final[int] = 500
# When full tracebacks are requested we raise the limit to 10k characters which
# aligns with the shared tooling's "debug" budget for interactive sessions.
_FULL_TRACEBACK_LIMIT: Final[int] = 10_000


def _module_main() -> int:
    """Execute the CLI entry point and return a normalized exit code.

    Why
        ``runpy.run_module("lib_layered_config.__main__", run_name="__main__")``
        should exhibit the exact same semantics as invoking the installed
        console script. Centralizing the logic here keeps error handling and
        traceback restoration consistent across both entry paths.

    What
        Calls :func:`lib_layered_config.cli.main` while temporarily
        disabling automatic traceback restoration so this wrapper can restore it
        after error handling completes. Any exception is delegated to
        :mod:`lib_cli_exit_tools` so exit codes follow the shared conventions.

    Returns
    -------
    int
        Exit code derived from the CLI run or mapped via
        :func:`lib_cli_exit_tools.get_system_exit_code` when an exception
        occurs.

    Side Effects
        Reads and writes ``lib_cli_exit_tools.config.traceback`` and writes to
        standard error via :func:`lib_cli_exit_tools.print_exception_message` on
        failure.

    Examples
    --------
    >>> from unittest.mock import patch
    >>> with patch("lib_layered_config.cli.main", return_value=0):
    ...     _module_main()
    0
    """

    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    try:
        try:
            return int(cli.main(restore_traceback=False))
        except BaseException as exc:  # fallback to shared exit helpers
            lib_cli_exit_tools.print_exception_message(
                trace_back=lib_cli_exit_tools.config.traceback,
                length_limit=(_FULL_TRACEBACK_LIMIT if lib_cli_exit_tools.config.traceback else _TRUNCATED_TRACEBACK_LIMIT),
            )
            return lib_cli_exit_tools.get_system_exit_code(exc)
    finally:
        lib_cli_exit_tools.config.traceback = previous_traceback


if __name__ == "__main__":
    raise SystemExit(_module_main())
