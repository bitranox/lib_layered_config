"""Placing many sibling keys stays linear in their number.

Every key placed by ``build_nested`` used to be matched case-insensitively against every key
already in its table, so N siblings cost N*N/2 comparisons: 30,000 keys took about 10 seconds,
which an ``.env`` file or an environment of that size turns into a startup stall.

The bound is wall clock on purpose. The quadratic path takes about 10 s here and the linear one
about 0.05 s, so a limit of 2.5 s leaves a slow CI runner room and still fails the old code by a
wide margin.
"""

from __future__ import annotations

import time
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
