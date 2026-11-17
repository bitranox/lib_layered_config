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
@pytest.mark.parametrize(
    "prefix",
    [
        "a" * _LETTERS + "! ",
        "a:" * (_LETTERS // 2),
        "x://" * (_LETTERS // 4) + " ",
        # One run per character class a scheme may hold, each glued to the URL, so no class is left
        # out of the bound: a scan that treats one of them differently is quadratic on that run alone.
        "a1" * (_LETTERS // 2),
        "a." * (_LETTERS // 2),
        "a-" * (_LETTERS // 2),
        "a+" * (_LETTERS // 2),
        "1:" * (_LETTERS // 2),
        "a1:" * (_LETTERS // 3),
    ],
    ids=["letters", "scheme-like-chain", "many-schemes", "digits", "dots", "dashes", "pluses", "digit-colons", "mixed"],
)
def test_a_long_run_before_a_url_is_scanned_in_linear_time(prefix: str) -> None:
    value = prefix + "x://u:pw@h"

    started = time.perf_counter()
    redacted = redact_mapping({"note": value})
    elapsed = time.perf_counter() - started

    assert redacted["note"].endswith(f"x://u:{REDACTED_PLACEHOLDER}@h")
    assert elapsed < _LIMIT_SECONDS, f"{len(prefix)} characters took {elapsed:.2f}s"
