"""A key deeper than the merge allows is refused by the env/.env loader, with the merge's own words.

User decision 2026-11-16 (R3-F2, "Refuse before building"): a key nesting past MAX_MERGE_DEPTH was
built a table per segment before the merge refused it. The loader now refuses it first, and every
input keeps the refusal it had: the same message for a key one level too deep, an empty segment
anywhere in a deep key, a shallower value blocking a deep key, and the shallowest of two deep keys.
"""

from __future__ import annotations

from typing import cast

import pytest

from lib_layered_config.adapters._nested_keys import NestedEntry, build_nested
from lib_layered_config.application.merge import MAX_MERGE_DEPTH
from tests.support.os_markers import os_agnostic

_TOO_DEEP = "configuration nesting exceeds the maximum depth of 100 at "


def _key(letter: str, segments: int) -> str:
    return "__".join([letter] * segments)


def _refusal(*entries: tuple[str, object]) -> str:
    with pytest.raises(ValueError) as caught:
        build_nested([NestedEntry(key, value, key[:12]) for key, value in entries], error_cls=ValueError)
    return str(caught.value)


def _depth_and_leaf(value: object) -> tuple[int, object]:
    """Follow the first key of each table down to the value at the bottom; count the tables passed."""
    depth = 0
    while isinstance(value, dict):
        value = next(iter(cast("dict[str, object]", value).values()))
        depth += 1
    return depth, value


@os_agnostic
def test_a_key_as_deep_as_the_merge_allows_is_built() -> None:
    nested = build_nested([NestedEntry(_key("A", MAX_MERGE_DEPTH + 1), 1, "deep")], error_cls=ValueError)

    assert _depth_and_leaf(nested) == (MAX_MERGE_DEPTH + 1, 1)


@os_agnostic
def test_one_level_deeper_is_refused_with_the_merge_s_message() -> None:
    message = _refusal((_key("A", MAX_MERGE_DEPTH + 2), 1))

    assert message.startswith(_TOO_DEEP + "a.a.a")
    assert message.endswith(" ...")


@os_agnostic
@pytest.mark.parametrize("tail", ["____x", "__"], ids=["doubled", "trailing"])
def test_an_empty_segment_past_the_depth_limit_is_still_named(tail: str) -> None:
    message = _refusal((_key("a", 200) + tail, 1))

    assert message.endswith("has an empty key segment (a leading, trailing or doubled '__')")


@os_agnostic
def test_a_value_blocking_a_deep_key_is_reported_as_the_collision() -> None:
    message = _refusal(("A", 1), (_key("a", 200), 2))

    assert message.startswith("A sets a to a value, so ")


@os_agnostic
def test_the_shallowest_of_two_deep_keys_is_named() -> None:
    message = _refusal((_key("a", 200), 1), (_key("B", 150), 2))

    assert message.startswith(_TOO_DEEP + "b.b.b")
