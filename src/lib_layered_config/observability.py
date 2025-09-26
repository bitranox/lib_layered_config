"""Structured logging helpers distilled into tiny orchestration phrases.

Purpose
    Keep every emission of logging data predictable, contextual, and ready for
    downstream aggregation pipelines without forcing applications to adopt a
    specific logging backend.

Contents
    - ``TRACE_ID``: context variable storing the active trace identifier.
    - ``get_logger``: returns the shared package logger (quiet by default).
    - ``bind_trace_id``: binds or clears the active trace identifier.
    - ``log_debug`` / ``log_info`` / ``log_error``: emit structured entries via a
      single private emitter.
    - ``make_event``: convenience builder for structured event payloads.

System Integration
    Used by adapters and the composition root to ensure all diagnostics carry
    the same trace metadata. Keeps the domain layer free from logging concerns
    while still offering consumers consistent observability hooks.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Final, Mapping

TRACE_ID: ContextVar[str | None] = ContextVar("lib_layered_config_trace_id", default=None)
"""Current trace identifier propagated through logging helpers.

Why
    Cross-cutting observability features (CLI, adapters) need a shared context
    without threading identifiers manually.
"""

_LOGGER: Final[logging.Logger] = logging.getLogger("lib_layered_config")
_LOGGER.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    """Expose the package logger so applications may attach handlers.

    Why
        Leaves the library silent by default while giving host applications full
        control over handler and formatter configuration.
    """

    return _LOGGER


def bind_trace_id(trace_id: str | None) -> None:
    """Bind or clear the active trace identifier.

    Why
        Correlates configuration events with external trace spans.
    What
        Stores ``trace_id`` in :data:`TRACE_ID`; ``None`` clears the binding.
    Inputs
        trace_id: Identifier string or ``None`` to drop the binding.
    Side Effects
        Mutates the context variable visible to subsequent logging helpers.

    Examples
    --------
    >>> bind_trace_id('abc123')
    >>> TRACE_ID.get()
    'abc123'
    >>> bind_trace_id(None)
    >>> TRACE_ID.get() is None
    True
    """

    TRACE_ID.set(trace_id)


def log_debug(message: str, **fields: Any) -> None:
    """Emit a structured debug log entry that includes the trace context."""

    _emit(logging.DEBUG, message, fields)


def log_info(message: str, **fields: Any) -> None:
    """Emit a structured info log entry that includes the trace context."""

    _emit(logging.INFO, message, fields)


def log_error(message: str, **fields: Any) -> None:
    """Emit a structured error log entry that includes the trace context."""

    _emit(logging.ERROR, message, fields)


def make_event(
    layer: str,
    path: str | None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured logging payload for configuration lifecycle events.

    Why
        Keeps event construction consistent so downstream log processors can rely
        on stable keys.
    What
        Returns a dictionary with ``layer`` and ``path`` keys and any optional
        payload fields.
    Inputs
        layer: Name of the configuration layer being observed.
        path: Filesystem path associated with the event, if available.
        payload: Optional mapping with extra diagnostic detail.
    Outputs
        dict[str, Any]: Data safe to unpack into :func:`log_*` helpers.

    Examples
    --------
    >>> make_event('env', None, {'keys': 3})
    {'layer': 'env', 'path': None, 'keys': 3}
    """

    event = _base_event(layer, path)
    return _merge_payload(event, payload)


def _emit(level: int, message: str, fields: Mapping[str, Any]) -> None:
    """Send a log entry through the shared logger with contextual metadata."""

    _LOGGER.log(level, message, extra={"context": _with_trace(fields)})


def _with_trace(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Attach the current trace identifier to the provided structured fields."""

    context = {"trace_id": TRACE_ID.get()}
    context.update(fields)
    return context


def _base_event(layer: str, path: str | None) -> dict[str, Any]:
    """Create the minimal event payload containing layer and path information."""

    return {"layer": layer, "path": path}


def _merge_payload(event: dict[str, Any], payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge optional diagnostic data into the event payload when provided."""

    if payload:
        event |= dict(payload)
    return event
