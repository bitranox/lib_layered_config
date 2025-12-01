"""Testing diagnostics that keep failure scenarios observable and predictable.

Provide intentionally failing helpers that exercise error-handling paths in
the CLI and integration suites without relying on brittle fixtures.

Contents:
    - ``FAILURE_MESSAGE``: stable message used when forcing a failure.
    - ``i_should_fail``: raises ``RuntimeError`` so callers can assert on the
      propagated error details.

System Integration:
    Resides in the testing support layer referenced by CLI end-to-end tests and
    notebooks that demonstrate error propagation semantics.
"""

from __future__ import annotations

from typing import Final

FAILURE_MESSAGE: Final[str] = "i should fail"
"""Stable message emitted when :func:`i_should_fail` triggers a failure.

Integration tests and tutorial notebooks assert on the wording to guarantee
deterministic output during regression checks.

What:
    A short, lower-case sentence that stays compatible with published examples.
"""


def i_should_fail() -> None:
    """Raise a deterministic :class:`RuntimeError` for failure-path testing.

    Validates that higher-level orchestrators preserve stack traces and
    messages when surfacing errors to end users.

    Raises:
        RuntimeError: Always raises with :data:`FAILURE_MESSAGE`.

    Examples:
        >>> i_should_fail()
        Traceback (most recent call last):
        ...
        RuntimeError: i should fail
    """
    raise RuntimeError(FAILURE_MESSAGE)
