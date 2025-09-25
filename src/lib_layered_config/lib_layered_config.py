"""Core demonstration helpers exercised by the CLI transport.

This module holds the minimal domain-level behaviors that the CLI exposes while
the real logging helpers are under construction. Keeping the greeting and
intentional failure logic here means the CLI can validate stdout handling and
error propagation without depending on yet-to-be-built Rich logging features.
Running the module as a script is intentionally blocked so transports remain the
only entry points and downstream documentation cannot accidentally diverge from
the supported usage.

Contents
--------
* :func:`hello_world` – emits the canonical greeting used in documentation and
  smoke tests. This gives developers a stable, human-readable success path.
* :func:`i_should_fail` – raises an intentional error so that failure handling
  and traceback controls can be validated end-to-end.
* :func:`main` – placeholder orchestration hook reserved for future transports
  that need a thin domain-level entry point.

System Context
--------------
The CLI adapter defined in :mod:`lib_layered_config.cli` delegates to
these helpers to keep the transport thin. The system design reference in
``docs/systemdesign/module_reference.md`` links back to this module so that the
relationship between the CLI surface and the placeholder domain logic remains
clear during incremental feature development.
"""

from __future__ import annotations


def hello_world() -> None:
    """Emit the canonical greeting used to verify the happy-path workflow.

    Why
        The scaffold ships with a deterministic success path so developers can
        check their packaging, CLI wiring, and documentation quickly without
        waiting for the richer logging helpers.

    What
        Prints the literal ``"Hello World"`` string followed by a newline to
        ``stdout``.

    Side Effects
        Writes directly to the process ``stdout`` stream.

    Examples
    --------
    >>> hello_world()
    Hello World
    """

    print("Hello World")


def i_should_fail() -> None:
    """Intentionally raise ``RuntimeError`` to test error propagation paths.

    Why
        The CLI and integration tests need a deterministic failure scenario to
        ensure traceback toggling and exit-code mapping stay correct as the
        project evolves.

    What
        Raises ``RuntimeError`` with the message ``"I should fail"`` every time
        it is called.

    Side Effects
        None besides raising the exception.

    Raises
        RuntimeError: Always, so downstream adapters can verify their error
        handling branches.

    Examples
    --------
    >>> i_should_fail()
    Traceback (most recent call last):
    ...
    RuntimeError: I should fail
    """

    raise RuntimeError("I should fail")


def main() -> None:
    """Reserved domain entry point to preserve future extensibility.

    Why
        Some transports expect a module-level `main` callable even when the
        domain layer stays import-only today. Keeping a placeholder ensures
        refactors can wire emerging behaviors without breaking imports.

    What
        Returns immediately without performing any work. Acts as an explicit
        seam where adapters may delegate once richer domain logic exists.

    Side Effects
        None. The function intentionally avoids I/O so that imports stay
        deterministic and tests can verify the placeholder contract.

    Examples
    --------
    >>> main()

    """

    return None


# Execution Guard
# ---------------
# The domain helpers are designed for import by CLI adapters and tests only.
# Import-time side effects must stay deterministic, so direct execution raises
# an error to steer developers toward the supported transport surfaces.
if __name__ == "__main__":
    raise SystemExit("This module is import-only and should not be executed directly. Use the CLI entry points instead.")
