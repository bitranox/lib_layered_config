"""Diagnostics helpers for exercising error paths during integration tests."""

from __future__ import annotations


def i_should_fail() -> None:
    """Intentionally raise :class:`RuntimeError` with a stable message.

    Why
        Some integration tests and CLI commands need a deterministic failure path
        to verify traceback handling and exit-code propagation.

    Raises
    ------
    RuntimeError
        Always raised with the message ``"i should fail"``.
    """

    raise RuntimeError("i should fail")
