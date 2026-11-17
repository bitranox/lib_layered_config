"""Placing many sibling keys stays linear in their number.

Every key placed by ``build_nested`` used to be matched case-insensitively against every key
already in its table, so N siblings cost N*N/2 comparisons: 30,000 keys took about 10 seconds,
which an ``.env`` file or an environment of that size turns into a startup stall.

The bound is wall clock on purpose. The quadratic path takes about 10 s here and the linear one
about 0.05 s, so a limit of 2.5 s leaves a slow CI runner room and still fails the old code by a
wide margin.
"""

from __future__ import annotations

import re
import time
import tracemalloc
from typing import TypeGuard

import pytest

from lib_layered_config.adapters._nested_keys import NestedEntry, build_nested

_SIBLINGS = 30_000
_LIMIT_SECONDS = 2.5


def _is_table(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("prefix", ["", "DB__"], ids=["top_level", "under_a_table"])
def test_many_sibling_keys_are_placed_in_linear_time(prefix: str) -> None:
    rows = [NestedEntry(f"{prefix}K{i}", i, f"{prefix}K{i}") for i in range(_SIBLINGS)]

    started = time.perf_counter()
    built = build_nested(rows, error_cls=ValueError)
    elapsed = time.perf_counter() - started

    table = built["db"] if prefix else built
    assert _is_table(table)
    assert len(table) == _SIBLINGS
    assert elapsed < _LIMIT_SECONDS, f"{_SIBLINGS} siblings took {elapsed:.2f}s"


@pytest.mark.os_agnostic
def test_a_repeated_key_in_another_case_keeps_its_first_spelling_and_last_value() -> None:
    rows = [NestedEntry("Timeout", 1, "a"), NestedEntry("TIMEOUT", 2, "b"), NestedEntry("timeout", 3, "c")]

    assert build_nested(rows, error_cls=ValueError) == {"timeout": 3}


@pytest.mark.os_agnostic
def test_a_deeper_key_reuses_a_json_table_key_in_its_original_case() -> None:
    rows = [NestedEntry("DB", {"Host": "h", "host": "shadowed"}, "DB"), NestedEntry("DB__HOST", "x", "DB__HOST")]

    assert build_nested(rows, error_cls=ValueError) == {"db": {"Host": "x", "host": "shadowed"}}


def _peak_bytes_refusing(segments: int) -> int:
    """Peak traced memory of build_nested refusing one key of *segments* segments."""
    key = "__".join(["a"] * segments)
    refusal = re.escape("configuration nesting exceeds the maximum depth of 100 at a.a.a")
    with pytest.raises(ValueError, match=refusal):  # warm imports and caches outside the measurement
        build_nested([NestedEntry(key, 1, key)], error_cls=ValueError)
    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match=refusal):
            build_nested([NestedEntry(key, 1, key)], error_cls=ValueError)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


@pytest.mark.os_agnostic
def test_a_key_deeper_than_the_merge_allows_is_refused_without_building_it() -> None:
    """User decision 2026-11-16 (R3-F2, "Refuse before building"): a key of a million segments built a
    table a million levels deep (685 MB for a 3 MB .env) only for the merge to refuse it past 100.
    The refusal now comes first and builds nothing below the depth it reports, so its memory stays a
    few times the key itself: measured 4.0-4.9x at 25k to 400k segments (the unsplit rest of the key
    and its lowercased copy), where building every level cost 222x."""
    segments = 100_000
    key_bytes = len("__".join(["a"] * segments))

    peak = _peak_bytes_refusing(segments)

    assert peak < 10 * key_bytes, f"refusing a {key_bytes}-byte key peaked at {peak} bytes"
