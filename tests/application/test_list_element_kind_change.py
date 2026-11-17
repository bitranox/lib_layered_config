"""A list element whose kind a higher layer changes keeps provenance by the table rule.

A table path forgets every entry below a node it replaces, and an empty table has an entry of its
own only while it is empty. A list element overridden by index (``PREFIX___DS__0``) did neither:
an element table replaced by a value kept its old leaves' entries, a value replaced by a table kept
the value's entry, and an element set to an empty table recorded nothing, so the display credited
the slot to the layer whose value it no longer holds.

The ``type_conflict`` warning names the kinds involved: a list is a ``list``, never a ``scalar``.
"""

from __future__ import annotations

import logging

import pytest

from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic


def _merge(*snapshots: LayerSnapshot) -> tuple[object, dict[str, str]]:
    """Merge *snapshots*; return the data under ``ds`` and each provenance key's layer."""
    result = merge_layers(list(snapshots))
    return result.data["ds"], {key: entry["layer"] for key, entry in result.provenance.items()}


_APP_TABLE_ELEMENT = LayerSnapshot(Layer.APP, {"ds": [{"a": 1}]}, "/etc/app.toml")
_APP_VALUE_ELEMENT = LayerSnapshot(Layer.APP, {"ds": [1]}, "/etc/app.toml")


@os_agnostic
def test_an_element_table_replaced_by_a_value_forgets_the_leaves_it_held() -> None:
    data, layers = _merge(
        _APP_TABLE_ELEMENT,
        LayerSnapshot(Layer.DOTENV, {"ds": {"0": {"a": "2"}}}, "/opt/app/.env"),
        LayerSnapshot(Layer.ENV, {"ds": {"0": "x"}}, None),
    )

    assert data == ["x"]
    assert layers == {"ds": "app", "ds.0": "env"}


@os_agnostic
def test_an_element_value_replaced_by_a_table_leaves_no_entry_for_the_table() -> None:
    data, layers = _merge(
        _APP_VALUE_ELEMENT,
        LayerSnapshot(Layer.DOTENV, {"ds": {"0": "2"}}, "/opt/app/.env"),
        LayerSnapshot(Layer.ENV, {"ds": {"0": {"b": "3"}}}, None),
    )

    assert data == [{"b": "3"}]
    assert layers == {"ds": "app", "ds.0.b": "env"}


@os_agnostic
def test_an_element_value_replaced_by_an_empty_table_names_the_layer_that_emptied_it() -> None:
    data, layers = _merge(
        _APP_VALUE_ELEMENT,
        LayerSnapshot(Layer.DOTENV, {"ds": {"0": "2"}}, "/opt/app/.env"),
        LayerSnapshot(Layer.ENV, {"ds": {"0": {}}}, None),
    )

    assert data == [{}]
    assert layers == {"ds": "app", "ds.0": "env"}


@os_agnostic
def test_an_empty_element_table_filled_later_has_no_entry_of_its_own() -> None:
    data, layers = _merge(
        _APP_VALUE_ELEMENT,
        LayerSnapshot(Layer.DOTENV, {"ds": {"0": {}}}, "/opt/app/.env"),
        LayerSnapshot(Layer.ENV, {"ds": {"0": {"c": "4"}}}, None),
    )

    assert data == [{"c": "4"}]
    assert layers == {"ds": "app", "ds.0.c": "env"}


def _type_conflict_kinds(caplog: pytest.LogCaptureFixture) -> list[tuple[object, object]]:
    """The ``(old_type, new_type)`` of every ``type_conflict`` event *caplog* holds."""
    kinds: list[tuple[object, object]] = []
    for record in caplog.records:
        if record.message == "type_conflict":
            context: dict[str, object] = record.__dict__["context"]
            kinds.append((context["old_type"], context["new_type"]))
    return kinds


@os_agnostic
@pytest.mark.parametrize(
    ("lower", "higher", "expected"),
    [
        ([1, 2], {"name": "x"}, ("list", "mapping")),
        ({"name": "x"}, [1, 2], ("mapping", "list")),
        ("on", {"name": "x"}, ("scalar", "mapping")),
        ({"name": "x"}, "off", ("mapping", "scalar")),
    ],
    ids=["list-to-table", "table-to-list", "value-to-table", "table-to-value"],
)
def test_a_type_conflict_names_the_real_kinds(
    lower: object, higher: object, expected: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="lib_layered_config"):
        merge_layers(
            [
                LayerSnapshot(Layer.APP, {"ds": lower}, "/etc/app.toml"),
                LayerSnapshot(Layer.USER, {"ds": higher}, "/opt/user.toml"),
            ]
        )

    assert _type_conflict_kinds(caplog) == [expected]
