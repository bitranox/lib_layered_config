from __future__ import annotations

import logging

import pytest

from lib_layered_config import bind_trace_id, get_logger
from lib_layered_config.observability import log_info


def test_null_handler_present() -> None:
    logger = get_logger()
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)


def test_trace_id_in_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="lib_layered_config")
    bind_trace_id("trace-123")
    log_info("merge-complete", layer="env", path=None)
    assert caplog.records
    record = caplog.records[-1]
    assert getattr(record, "context") == {"trace_id": "trace-123", "layer": "env", "path": None}
