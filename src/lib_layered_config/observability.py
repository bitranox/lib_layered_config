"""Structured logging helpers for adapters.

Purpose
-------
Provide structured logging primitives with optional trace identifiers. All
logging performed by ``lib_layered_config`` flows through this module so callers
can integrate with their observability pipeline.

Contents
--------
* :data:`TRACE_ID` – context variable storing the current trace identifier.
* :func:`get_logger` – returns the package logger (pre-configured with a
  ``NullHandler``).
* :func:`bind_trace_id` – set/reset the active trace ID.
* :func:`log_debug`, :func:`log_info`, :func:`log_error` – structured logging
  helpers that attach the trace context and arbitrary fields.
* :func:`make_event` – convenience helper for building structured payloads.

System Role
-----------
Cross-cutting helper used by adapters and the composition root to emit
structured diagnostics without depending on application-specific logging
configuration.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Mapping

TRACE_ID: ContextVar[str | None] = ContextVar("lib_layered_config_trace_id", default=None)
"""Context variable holding the active trace identifier (if any)."""

_LOGGER = logging.getLogger("lib_layered_config")
_LOGGER.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    """Return the package logger preconfigured with a ``NullHandler``.

    Why
    ----
    Expose the logger so applications can attach handlers/formatters while the
    library stays quiet by default.
    """

    return _LOGGER


def log_debug(message: str, **fields: Any) -> None:
    """Emit a structured debug log entry.

    Why
    ----
    Provide consistent payload shape across adapters for low-level diagnostics.

    Parameters
    ----------
    message:
        Log message name (used as event identifier).
    **fields:
        Additional structured metadata (merged with the active trace id).
    """

    extra = {"trace_id": TRACE_ID.get(), **fields}
    _LOGGER.debug(message, extra={"context": extra})


def log_info(message: str, **fields: Any) -> None:
    """Emit a structured info log entry matching :func:`log_debug` semantics.

    Why
    ----
    Surface high-level configuration lifecycle events (layer loaded, merged,
    etc.).
    """

    extra = {"trace_id": TRACE_ID.get(), **fields}
    _LOGGER.info(message, extra={"context": extra})


def bind_trace_id(trace_id: str | None) -> None:
    """Bind (or clear) the active trace identifier used by logging helpers.

    Why
    ----
    Allow callers to correlate configuration events with external traces.

    Parameters
    ----------
    trace_id:
        Identifier string or ``None`` to clear the current binding.

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


def log_error(message: str, **fields: Any) -> None:
    """Emit a structured error log entry matching :func:`log_debug` semantics.

    Why
    ----
    Capture parsing failures or other recoverable errors with trace context.
    """

    extra = {"trace_id": TRACE_ID.get(), **fields}
    _LOGGER.error(message, extra={"context": extra})


def make_event(layer: str, path: str | None, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a structured dict representing a configuration event.

    Why
    ----
    Keep event construction consistent across adapters so log aggregation can
    rely on stable keys.

    Parameters
    ----------
    layer:
        Name of the configuration layer involved in the event.
    path:
        Filesystem path (if available) that triggered the event.
    payload:
        Optional mapping of additional diagnostic information (e.g. number of
        files processed).

    Returns
    -------
    dict[str, Any]
        Structured dictionary safe to pass as ``**fields`` to logging helpers.

    Examples
    --------
    >>> make_event('env', None, {'keys': 3})
    {'layer': 'env', 'path': None, 'keys': 3}
    """

    data = {"layer": layer, "path": path}
    if payload:
        data |= dict(payload)
    return data
