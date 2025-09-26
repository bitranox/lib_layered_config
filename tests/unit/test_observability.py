"""Unit tests for structured logging utilities in ``observability``.

Validates the null handler, trace binding, and event construction behaviour the
module reference promises to downstream consumers.
"""

from __future__ import annotations

import logging

import pytest

from lib_layered_config import bind_trace_id, get_logger
from lib_layered_config.observability import TRACE_ID, log_info, make_event


def test_null_handler_present() -> None:
    """Package logger should always include a NullHandler to avoid surprises."""

    logger = get_logger()
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)


def test_trace_id_in_log(caplog: pytest.LogCaptureFixture) -> None:
    """Structured logs should include the bound trace identifier and contextual fields."""

    caplog.set_level(logging.INFO, logger="lib_layered_config")
    bind_trace_id("trace-123")
    log_info("merge-complete", layer="env", path=None)
    assert caplog.records
    record = caplog.records[-1]
    assert getattr(record, "context") == {"trace_id": "trace-123", "layer": "env", "path": None}


def test_bind_trace_id_clears_context() -> None:
    """Clearing the trace ID should reset the context variable to None."""

    bind_trace_id("trace-temp")
    bind_trace_id(None)
    assert TRACE_ID.get() is None


def test_make_event_merges_optional_payload() -> None:
    """make_event should merge optional metadata without mutating base keys."""

    event = make_event("env", None, {"keys": 3})
    assert event == {"layer": "env", "path": None, "keys": 3}
