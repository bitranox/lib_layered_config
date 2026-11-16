"""Replacing many containers across layers stays linear in their number.

Each container a later layer replaced (a table by a value, a list by a table) used to scan every
provenance entry for the keys below it, so N replacements over N entries cost N*N: 16,000 of them
took about 4 seconds, and the time quadrupled with each doubling.

The test bounds how the time GROWS, not the time itself: a fixed limit measured the machine, and an
older CPU runs this merge about 9x slower per container whatever the size. Eight times the
containers take about 8x the time on the linear path and about 50x on a quadratic one (measured on
Linux and Windows, best of three runs each), so a limit of 20x leaves room for noise either way.
"""

from __future__ import annotations

import time

import pytest

from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer

_SMALL = 1_000
_LARGE = 8_000
_MAX_GROWTH = 20.0
_RUNS = 3


def _shapes(kind: str, count: int) -> tuple[dict[str, object], dict[str, object]]:
    if kind == "table_to_value":
        return {f"t{i}": {"x": 1} for i in range(count)}, {f"t{i}": 1 for i in range(count)}
    return {f"t{i}": [1] for i in range(count)}, {f"t{i}": {"x": 1} for i in range(count)}


def _best_merge_seconds(kind: str, count: int) -> float:
    """The fastest of a few merges of *count* replaced containers: the least disturbed by other load."""
    timings: list[float] = []
    for _ in range(_RUNS):
        low, high = _shapes(kind, count)
        layers = [LayerSnapshot(Layer.APP, low, "/opt/app.toml"), LayerSnapshot(Layer.USER, high, "/opt/user.toml")]
        started = time.perf_counter()
        result = merge_layers(layers)
        timings.append(time.perf_counter() - started)
        assert len(result.data) == count
    return min(timings)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("kind", ["table_to_value", "list_to_table"])
def test_many_replaced_containers_are_merged_in_linear_time(kind: str) -> None:
    small = _best_merge_seconds(kind, _SMALL)
    large = _best_merge_seconds(kind, _LARGE)

    growth = large / small
    times = f"{small:.3f}s for {_SMALL}, {large:.3f}s for {_LARGE}"
    assert growth < _MAX_GROWTH, f"{_LARGE // _SMALL}x the containers took {growth:.1f}x the time ({times})"


@pytest.mark.os_agnostic
def test_a_container_replaced_twice_forgets_the_keys_of_each_version() -> None:
    layers = [
        LayerSnapshot(Layer.DEFAULTS, {"db": {"host": "h", "pool": {"size": 1}}, "dbx": 1}, None),
        LayerSnapshot(Layer.APP, {"db": "flat"}, None),
        LayerSnapshot(Layer.HOST, {"db": {"port": 2}}, None),
        LayerSnapshot(Layer.USER, {"db": "flat again"}, None),
    ]

    result = merge_layers(layers)

    assert result.data == {"db": "flat again", "dbx": 1}
    assert sorted(result.provenance) == ["db", "dbx"]
    assert result.provenance["db"]["layer"] == "user"


@pytest.mark.os_agnostic
def test_merge_result_provenance_is_a_plain_dict_in_merge_order() -> None:
    layers = [LayerSnapshot(Layer.APP, {"b": 1, "a": {"c": 2}}, None), LayerSnapshot(Layer.ENV, {"z": 3}, None)]

    result = merge_layers(layers)

    assert type(result.provenance) is dict
    assert list(result.provenance) == ["b", "a.c", "z"]
