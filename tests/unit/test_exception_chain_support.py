"""The shared exception-chain walker reaches every link, not just one path."""

from __future__ import annotations

from tests.support.exception_chain import carries, chain
from tests.support.os_markers import os_agnostic


def _caught_with_cause_and_a_different_context() -> BaseException:
    try:
        try:
            raise KeyError("only in __context__")
        except KeyError:
            raise ValueError("outer") from OSError("only in __cause__")
    except ValueError as caught:
        return caught
    raise AssertionError("unreachable")


@os_agnostic
def test_the_walk_reaches_a_context_link_beside_a_cause() -> None:
    names = [type(link).__name__ for link in chain(_caught_with_cause_and_a_different_context())]
    assert names == ["ValueError", "OSError", "KeyError"]


@os_agnostic
def test_carries_finds_a_kind_that_sits_only_in_the_context() -> None:
    assert carries(_caught_with_cause_and_a_different_context(), KeyError)


@os_agnostic
def test_a_cycle_is_walked_once() -> None:
    first = ValueError("first")
    second = OSError("second")
    first.__context__ = second
    second.__context__ = first
    assert chain(first) == [first, second]
