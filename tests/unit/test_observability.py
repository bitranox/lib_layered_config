"""Observability helpers expressed as concise tests."""

from __future__ import annotations

import logging

import pytest

from lib_layered_config import bind_trace_id, get_logger
from lib_layered_config.observability import TRACE_ID, log_info, make_event, _merge_payload

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_logger_decorates_itself_with_null_handler() -> None:
    logger = get_logger()
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)


@os_agnostic
def test_log_info_carries_trace_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="lib_layered_config")
    bind_trace_id("trace-123")
    log_info("merge-complete", layer="env", path=None)
    record = caplog.records[-1]
    assert getattr(record, "context") == {"trace_id": "trace-123", "layer": "env", "path": None}


@os_agnostic
def test_bind_trace_id_none_clears_context_variable() -> None:
    bind_trace_id("trace-temp")
    bind_trace_id(None)
    assert TRACE_ID.get() is None


@os_agnostic
def test_make_event_merges_optional_payload_without_losing_base_fields() -> None:
    event = make_event("env", None, {"keys": 3})
    assert event == {"layer": "env", "path": None, "keys": 3}


@os_agnostic
def test_merge_payload_returns_original_when_payload_missing() -> None:
    event = {"layer": "env"}
    result = _merge_payload(event, None)
    assert result == {"layer": "env"}


@os_agnostic
def test_merge_payload_merges_copy_of_payload() -> None:
    event = {"layer": "env"}
    payload = {"keys": 2}
    result = _merge_payload(event, payload)
    assert result == {"layer": "env", "keys": 2}
