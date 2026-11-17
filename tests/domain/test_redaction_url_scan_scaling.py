"""Looking for URLs anywhere in a value stays linear in the value's length.

Redaction masks the password of every URL in a string value, so it searches the whole value for a
``scheme://``. A search that may start at any position rescans a long run of letters from each of its
positions when no ``://`` follows the run: 20,000 letters took about 3 s, and a long token or base64
blob in a configuration value would stall every redacted view.

The bound is wall clock on purpose. At 40,000 letters the linear search takes about 1 ms and the
quadratic one about 12 s, so a limit of 1 s leaves a slow CI runner room and still fails the old code
by a wide margin.
"""

from __future__ import annotations

import time

import pytest

from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, redact_mapping

_LETTERS = 40_000
_LIMIT_SECONDS = 1.0


@pytest.mark.os_agnostic
def test_a_long_run_of_letters_before_a_url_is_scanned_in_linear_time() -> None:
    value = "a" * _LETTERS + "! x://u:pw@h"

    started = time.perf_counter()
    redacted = redact_mapping({"note": value})
    elapsed = time.perf_counter() - started

    assert redacted == {"note": "a" * _LETTERS + f"! x://u:{REDACTED_PLACEHOLDER}@h"}
    assert elapsed < _LIMIT_SECONDS, f"{_LETTERS} letters took {elapsed:.2f}s"
