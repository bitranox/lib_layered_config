"""Replacing many containers across layers stays linear in their number.

Each container a later layer replaced (a table by a value, a list by a table) used to scan every
provenance entry for the keys below it, so N replacements over N entries cost N*N: 16,000 of them
took about 4 seconds, and the time quadrupled with each doubling.

The bound is wall clock on purpose. The quadratic path takes about 9 s for the size below and the
linear one well under a second, so a limit of 2.5 s leaves a slow CI runner room and still fails
the old code by a wide margin.
"""

from __future__ import annotations

import time

import pytest

from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer

_CONTAINERS = 24_000
_LIMIT_SECONDS = 2.5


def _shapes(kind: str) -> tuple[dict[str, object], dict[str, object]]:
    if kind == "table_to_value":
        return {f"t{i}": {"x": 1} for i in range(_CONTAINERS)}, {f"t{i}": 1 for i in range(_CONTAINERS)}
    return {f"t{i}": [1] for i in range(_CONTAINERS)}, {f"t{i}": {"x": 1} for i in range(_CONTAINERS)}


@pytest.mark.os_agnostic
@pytest.mark.parametrize("kind", ["table_to_value", "list_to_table"])
def test_many_replaced_containers_are_merged_in_linear_time(kind: str) -> None:
    low, high = _shapes(kind)
    layers = [LayerSnapshot(Layer.APP, low, "/opt/app.toml"), LayerSnapshot(Layer.USER, high, "/opt/user.toml")]

    started = time.perf_counter()
    result = merge_layers(layers)
    elapsed = time.perf_counter() - started

    assert len(result.data) == _CONTAINERS
    assert elapsed < _LIMIT_SECONDS, f"{_CONTAINERS} replaced containers took {elapsed:.2f}s"


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
