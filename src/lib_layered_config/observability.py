"""Structured logging helpers distilled into tiny orchestration phrases.

Keep every emission of logging data predictable, contextual, and ready for
downstream aggregation pipelines without forcing applications to adopt a
specific logging backend.

Contents:
    - ``TRACE_ID``: context variable storing the active trace identifier.
    - ``get_logger``: returns the shared package logger (quiet by default).
    - ``bind_trace_id``: binds or clears the active trace identifier.
    - ``log_debug`` / ``log_info`` / ``log_warn`` / ``log_error``: emit structured
      entries via a single private emitter.
    - ``make_event``: convenience builder for structured event payloads.

System Integration:
    Used by adapters and the composition root to ensure all diagnostics carry
    the same trace metadata. Keeps the domain layer free from logging concerns
    while still offering consumers consistent observability hooks.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any, Final

TRACE_ID: ContextVar[str | None] = ContextVar("lib_layered_config_trace_id", default=None)
"""Current trace identifier propagated through logging helpers.

Cross-cutting observability features (CLI, adapters) need a shared context without threading identifiers manually.

Context variable storing a string identifier or ``None``.
"""

_LOGGER: Final[logging.Logger] = logging.getLogger("lib_layered_config")
_LOGGER.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    """Expose the package logger so applications may attach handlers.

    Leave the library silent by default while giving host applications full control over handler configuration.

    Returns:
        logging.Logger: Shared logger instance for ``lib_layered_config``.
    """
    return _LOGGER


def bind_trace_id(trace_id: str | None) -> None:
    """Bind or clear the active trace identifier.

    Correlate configuration events with external trace spans.

    Args:
        trace_id: Identifier string or ``None`` to drop the binding.

    Side Effects:
        Mutates :data:`TRACE_ID`, affecting subsequent logging helpers.

    Examples:
        >>> bind_trace_id('abc123')
        >>> TRACE_ID.get()
        'abc123'
        >>> bind_trace_id(None)
        >>> TRACE_ID.get() is None
        True
    """
    TRACE_ID.set(trace_id)


def log_debug(message: str, **fields: Any) -> None:
    """Emit a structured debug log entry that includes the trace context.

    Provide consistent debug telemetry across adapters while threading trace metadata.

    Args:
        message: Event name rendered by the logger.
        **fields: Structured context merged into the payload.

    Side Effects:
        Calls :func:`_emit`, which writes to the shared logger.
    """
    _emit(logging.DEBUG, message, fields)


def log_info(message: str, **fields: Any) -> None:
    """Emit a structured info log entry that includes the trace context.

    Capture high-level lifecycle events (layer loaded, merge complete) with trace IDs attached.

    Args:
        message: Event name rendered by the logger.
        **fields: Structured context merged into the payload.

    Side Effects:
        Calls :func:`_emit` with ``logging.INFO``.
    """
    _emit(logging.INFO, message, fields)


def log_warn(message: str, **fields: Any) -> None:
    """Emit a structured warning log entry that includes the trace context.

    Surface potential configuration issues (e.g., type conflicts) that don't prevent
    loading but may indicate user error.
    """
    _emit(logging.WARNING, message, fields)


def log_error(message: str, **fields: Any) -> None:
    """Emit a structured error log entry that includes the trace context.

    Surface recoverable adapter failures (e.g., invalid files) with enough context for diagnosis.
    """
    _emit(logging.ERROR, message, fields)


def make_event(
    layer: str,
    path: str | None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured logging payload for configuration lifecycle events.

    Keep event construction consistent so downstream log processors can rely on stable keys.

    Args:
        layer: Name of the configuration layer being observed.
        path: Filesystem path associated with the event, if available.
        payload: Optional mapping with extra diagnostic detail.

    Returns:
        dict[str, Any]: Data safe to unpack into :func:`log_debug`, :func:`log_info`, :func:`log_warn`, or :func:`log_error`.

    Examples:
        >>> make_event('env', None, {'keys': 3})
        {'layer': 'env', 'path': None, 'keys': 3}
    """
    event = _base_event(layer, path)
    return _merge_payload(event, payload)


def _emit(level: int, message: str, fields: Mapping[str, Any]) -> None:
    """Send a log entry through the shared logger with contextual metadata.

    Centralise the call to ``logging.Logger.log`` so trace injection and field handling stay consistent.

    Args:
        level: Standard library logging level.
        message: Event name rendered by the logger.
        fields: Structured payload to merge with the trace identifier.

    Side Effects:
        Writes to the shared package logger.
    """
    _LOGGER.log(level, message, extra={"context": _with_trace(fields)})


def _with_trace(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Attach the current trace identifier to the provided structured fields.

    Guarantee that every log entry includes the active trace (when present).

    Args:
        fields: Mapping of additional structured context.

    Returns:
        dict[str, Any]: Copy of ``fields`` with ``trace_id`` added.
    """
    context = {"trace_id": TRACE_ID.get()}
    context.update(fields)
    return context


def _base_event(layer: str, path: str | None) -> dict[str, Any]:
    """Create the minimal event payload containing layer and path information.

    Provide a consistent foundation for layer-related logging events.

    Args:
        layer: Layer name to annotate the event.
        path: Optional filesystem path associated with the event.

    Returns:
        dict[str, Any]: Base payload ready for augmentation.
    """
    return {"layer": layer, "path": path}


def _merge_payload(event: dict[str, Any], payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge optional diagnostic data into the event payload when provided.

    Allow callers to enrich events without mutating the original dictionary outside this helper.

    Args:
        event: Base event payload.
        payload: Optional mapping of diagnostic data.

    Returns:
        dict[str, Any]: Updated payload containing merged data.

    Side Effects:
        Mutates ``event`` when ``payload`` is provided.
    """
    if payload:
        event |= dict(payload)
    return event
