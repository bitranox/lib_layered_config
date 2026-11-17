"""Looking a key up in a ``Config`` costs that key, not the size of the section around it.

A read of a table hands back a copy (the immutability contract), so a lookup that goes through a read
copies the whole section just to answer yes or no; and a dotted ``get`` that checks every key of each
table it passes is linear in the table's size. Both are measured against the section size: memory by
tracemalloc's peak, time by how it grows from a small section to one 128 times the size.
"""

from __future__ import annotations

import time
import tracemalloc

from lib_layered_config.domain.config import Config
from tests.support.os_markers import os_agnostic

_SMALL = 1_000
_LARGE = 128_000


def _config(size: int) -> Config:
    return Config({"section": {f"k{index}": index for index in range(size)}}, {})


def _best_time(cfg: Config, calls: int = 200, rounds: int = 5) -> float:
    best = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        for _ in range(calls):
            cfg.get("section.k0")
        best = min(best, time.perf_counter() - start)
    return best


@os_agnostic
def test_a_membership_test_copies_nothing() -> None:
    cfg = _config(20_000)
    _ = "section" in cfg  # warm imports and caches outside the measurement

    tracemalloc.start()
    try:
        found = "section" in cfg
        missing = "absent" in cfg
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert (found, missing) == (True, False)
    # A copy of the 20 000-key section is about a megabyte; the answer itself needs a few hundred bytes.
    assert peak < 16_384


@os_agnostic
def test_a_dotted_get_does_not_grow_with_the_section_it_passes() -> None:
    small, large = _config(_SMALL), _config(_LARGE)

    ratio = _best_time(large) / _best_time(small)

    # A lookup that checks every key grows with the section, about 128 times here; one that does not
    # stays near 1. The bound leaves room for a loaded CI host.
    assert ratio < 8, f"get on a {_LARGE}-key section took {ratio:.1f} times as long as on {_SMALL} keys"
