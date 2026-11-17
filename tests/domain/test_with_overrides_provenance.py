"""``Config.with_overrides`` keeps provenance by the rule the merge uses for an empty table.

The merge gives a table an entry of its own only while the table is empty: an empty table
declared in one layer and filled by a later one reports its values' origins, never the empty
declaration's. ``with_overrides`` kept the empty declaration's entry after the override filled the
table, so ``origin("styles")`` named a file whose table no longer held what the config shows.
Each test does the same change as a later merge layer and as an override and compares the keys
that carry an entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_layered_config import OVERRIDE_LAYER, Config
from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def _config_from(payload: Mapping[str, object]) -> Config:
    """A ``Config`` built the way ``read_config`` builds one, from a single app layer."""
    result = merge_layers([LayerSnapshot(Layer.APP, payload, "/etc/app.toml")])
    return Config(result.data, result.provenance)


def _keys_merged_as_a_layer(base: Mapping[str, object], change: Mapping[str, object]) -> set[str]:
    """The provenance keys when *change* arrives as a later merge layer over *base*."""
    snapshots = [LayerSnapshot(Layer.APP, base, "/etc/app.toml"), LayerSnapshot(Layer.USER, change, "/opt/user.toml")]
    return set(merge_layers(snapshots).provenance)


def _keys_with_an_origin(config: Config, candidates: Iterable[str]) -> set[str]:
    """The *candidates* that ``config.origin`` answers for."""
    return {key for key in candidates if config.origin(key) is not None}


@os_agnostic
def test_an_empty_table_filled_by_an_override_has_no_entry_of_its_own() -> None:
    base: dict[str, object] = {"styles": {}}
    change: dict[str, object] = {"styles": {"DEBUG": "dim"}}

    config = _config_from(base).with_overrides(change)

    assert _keys_with_an_origin(config, {"styles", "styles.DEBUG"}) == _keys_merged_as_a_layer(base, change)
    assert config.origin("styles") is None


@os_agnostic
def test_a_nested_empty_table_filled_by_an_override_drops_only_its_own_entry() -> None:
    base: dict[str, object] = {"a": {"b": {}, "keep": 1}}
    change: dict[str, object] = {"a": {"b": {"c": 2}}}

    config = _config_from(base).with_overrides(change)

    candidates = {"a", "a.b", "a.b.c", "a.keep"}
    assert _keys_with_an_origin(config, candidates) == _keys_merged_as_a_layer(base, change)
    assert config.origin("a.keep") == {"layer": "app", "path": "/etc/app.toml", "key": "a.keep"}


@os_agnostic
def test_an_empty_table_declared_empty_again_by_an_override_names_the_override() -> None:
    """The merge credits an empty table to the last layer declaring it; an override is that layer."""
    config = _config_from({"styles": {}}).with_overrides({"styles": {}})

    assert config.origin("styles") == {"layer": OVERRIDE_LAYER, "path": None, "key": "styles"}
