from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.application.merge import LayerSnapshot, MergeResult, merge_layers
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic


def _deeply_nested(depth: int) -> dict[str, object]:
    root: dict[str, object] = {}
    node = root
    for _ in range(depth):
        child: dict[str, object] = {}
        node["k"] = child
        node = child
    return root


@os_agnostic
def test_when_nesting_is_pathologically_deep_merge_raises_invalid_format() -> None:
    with pytest.raises(InvalidFormatError):
        merge_story(snapshot("app", _deeply_nested(150)))


def _nested_contains(actual: object | None, expected: object) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(_nested_contains(actual.get(key), value) for key, value in expected.items())
    return actual == expected


SCALAR = st.one_of(st.booleans(), st.integers(), st.text(min_size=1, max_size=5))
VALUE = st.recursive(
    SCALAR,
    lambda children: st.dictionaries(st.text(min_size=1, max_size=5), children, max_size=3),
    max_leaves=10,
)
MAPPING = st.dictionaries(st.text(min_size=1, max_size=5), VALUE, max_size=4)


def snapshot(name: str, payload: dict[str, object], origin: str | None = None) -> LayerSnapshot:
    return LayerSnapshot(name, payload, origin)


def merge_story(*layers: LayerSnapshot) -> MergeResult:
    return merge_layers(list(layers))


@os_agnostic
def test_when_user_layer_sings_last_word_the_scalar_agrees() -> None:
    result = merge_story(
        snapshot("app", {"feature": {"enabled": False}}, "app.toml"),
        snapshot("user", {"feature": {"enabled": True}}, "user.toml"),
    )
    assert result.data["feature"]["enabled"] is True


@os_agnostic
def test_when_env_layer_whispers_new_key_the_story_remembers() -> None:
    result = merge_story(
        snapshot("app", {"feature": {}}, "app.toml"),
        snapshot("env", {"feature": {"level": "debug"}}),
    )
    assert result.data["feature"]["level"] == "debug"


@os_agnostic
def test_when_user_layer_overrides_provenance_points_to_user() -> None:
    result = merge_story(
        snapshot("app", {"feature": {"enabled": False}}, "app.toml"),
        snapshot("user", {"feature": {"enabled": True}}, "user.toml"),
    )
    assert result.provenance["feature.enabled"]["layer"] == "user"


@os_agnostic
def test_when_env_layer_adds_key_provenance_points_to_env() -> None:
    result = merge_story(
        snapshot("app", {"feature": {}}, "app.toml"),
        snapshot("env", {"feature": {"level": "debug"}}),
    )
    assert result.provenance["feature.level"]["layer"] == "env"


@os_agnostic
def test_when_dotenv_supplies_password_the_payload_keeps_it() -> None:
    result = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("dotenv", {"db": {"password": "secret"}}, ".env"),
    )
    assert result.data["db"]["password"] == "secret"


@os_agnostic
def test_when_scalar_replaced_by_empty_dict_provenance_points_to_new_layer() -> None:
    """When a scalar is replaced by an empty dict, provenance should track the new layer."""
    result = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": {}}}),
    )
    # The empty dict came from env layer, so provenance should point there
    assert result.provenance["db.host"]["layer"] == "env"


@os_agnostic
def test_when_layer_defines_empty_dict_provenance_is_recorded() -> None:
    """Empty dicts should have provenance so display can show their source."""
    result = merge_story(
        snapshot("app", {"styles": {}, "enabled": True}, "app.toml"),
    )
    assert result.provenance["styles"]["layer"] == "app"
    assert result.provenance["styles"]["path"] == "app.toml"
    assert result.provenance["enabled"]["layer"] == "app"


@os_agnostic
def test_when_merging_twice_the_payload_stays_the_same() -> None:
    first = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    second = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    assert first.data == second.data


@os_agnostic
def test_when_merging_twice_the_metadata_sings_the_same_tune() -> None:
    first = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    second = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    assert first.provenance == second.provenance


@os_agnostic
def test_when_original_list_changes_the_merged_copy_stays_still() -> None:
    payload = {"numbers": [1, 2]}
    result = merge_story(snapshot("env", payload))
    payload["numbers"].append(3)
    assert result.data["numbers"] == [1, 2]


@os_agnostic
def test_when_original_dict_changes_the_merged_copy_stays_still() -> None:
    payload = {"nested": {"child": "value"}}
    result = merge_story(snapshot("env", payload))
    payload["nested"]["child"] = "changed"
    assert result.data["nested"]["child"] == "value"


@os_agnostic
def test_when_original_set_changes_the_merged_copy_stays_still() -> None:
    payload = {"choices": {1, 2}}
    result = merge_story(snapshot("env", payload))
    payload["choices"].add(3)
    assert result.data["choices"] == {1, 2}


@os_agnostic
def test_when_original_dict_with_nonstring_keys_changes_the_copy_stays_still() -> None:
    payload = {"strange": {1: "value"}}
    result = merge_story(snapshot("env", payload))
    payload["strange"][1] = "changed"
    assert result.data["strange"][1] == "value"


@os_agnostic
def test_when_original_tuple_travels_through_merge_it_returns_intact() -> None:
    payload = {"paths": ("one", "two")}
    result = merge_story(snapshot("env", payload))
    assert result.data["paths"] == ("one", "two")


@os_agnostic
@given(MAPPING, MAPPING, MAPPING)
def test_associativity_holds_like_a_round_song(lhs, mid, rhs) -> None:
    left = merge_story(snapshot("lhs", lhs), snapshot("mid", mid), snapshot("rhs", rhs))
    step_one = merge_story(snapshot("lhs-mid", left.data), snapshot("rhs", rhs))
    mid_then_right = merge_story(snapshot("mid", mid), snapshot("rhs", rhs))
    step_two = merge_story(snapshot("lhs", lhs), snapshot("mid-rhs", mid_then_right.data))
    assert step_one.data == step_two.data


@os_agnostic
@given(MAPPING, MAPPING)
def test_latest_non_empty_layer_wins_like_a_final_verse(first, second) -> None:
    result = merge_story(snapshot("first", first), snapshot("second", second))
    chorus = all(
        _nested_contains(result.data.get(key), value)
        for key, value in second.items()
        if not (isinstance(value, dict) and not value)
    )
    assert chorus is True


@os_agnostic
def test_when_env_numbers_a_slot_the_list_keeps_its_shape() -> None:
    """A numeric-key mapping over an existing list overrides that element and stays a list."""
    result = merge_story(
        snapshot("app", {"dataset": [{"name": "a", "port": 5}, {"name": "b"}]}, "app.toml"),
        snapshot("env", {"dataset": {"0": {"name": "x"}}}),
    )
    assert isinstance(result.data["dataset"], list)
    assert result.data["dataset"][0] == {"name": "x", "port": 5}
    assert result.data["dataset"][1] == {"name": "b"}


@os_agnostic
def test_when_env_indexes_past_the_end_it_appends_the_new_verse() -> None:
    result = merge_story(
        snapshot("app", {"hosts": [{"name": "a"}]}, "app.toml"),
        snapshot("env", {"hosts": {"1": {"name": "b"}}}),
    )
    assert result.data["hosts"] == [{"name": "a"}, {"name": "b"}]


@os_agnostic
def test_when_env_index_leaps_beyond_the_next_slot_it_warns_and_skips(caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    result = merge_story(
        snapshot("app", {"hosts": [{"name": "a"}]}, "app.toml"),
        snapshot("env", {"hosts": {"5": {"name": "z"}}}),
    )
    assert result.data["hosts"] == [{"name": "a"}]
    assert any(record.message == "list_index_out_of_range" for record in caplog.records)


@os_agnostic
def test_when_numeric_keys_have_no_list_they_stay_a_dict() -> None:
    """Without an underlying list the numeric segments keep their current dict semantics."""
    result = merge_story(
        snapshot("env", {"shards": {"0": "a", "1": "b"}}),
    )
    assert result.data["shards"] == {"0": "a", "1": "b"}


@os_agnostic
def test_when_mapping_mixes_numbers_and_words_over_a_list_it_stays_current_behavior() -> None:
    """Mixed numeric/alpha keys do NOT trigger index merge; today's replace behavior stands."""
    result = merge_story(
        snapshot("app", {"items": [{"name": "a"}]}, "app.toml"),
        snapshot("env", {"items": {"0": {"name": "x"}, "label": "top"}}),
    )
    assert result.data["items"] == {"0": {"name": "x"}, "label": "top"}


@os_agnostic
def test_when_env_overrides_element_provenance_points_to_env() -> None:
    result = merge_story(
        snapshot("app", {"dataset": [{"dsn": "old"}]}, "app.toml"),
        snapshot("env", {"dataset": {"0": {"dsn": "new"}}}),
    )
    assert result.data["dataset"][0]["dsn"] == "new"
    assert result.provenance["dataset.0.dsn"]["layer"] == "env"


@os_agnostic
def test_when_env_indexes_a_nested_list_it_overrides_one_cell() -> None:
    """A nested array-of-arrays keeps its inner list; only the addressed cell changes."""
    result = merge_story(
        snapshot("app", {"matrix": [[1, 2], [3, 4]]}, "app.toml"),
        snapshot("env", {"matrix": {"0": {"0": 9}}}),
    )
    assert result.data["matrix"] == [[9, 2], [3, 4]]


@os_agnostic
def test_when_env_replaces_element_with_scalar_it_swaps_the_slot() -> None:
    result = merge_story(
        snapshot("app", {"ports": [{"n": 1}, {"n": 2}]}, "app.toml"),
        snapshot("env", {"ports": {"0": 8080}}),
    )
    assert result.data["ports"] == [8080, {"n": 2}]


@os_agnostic
def test_when_scalar_overwrites_mapping_a_warning_is_emitted(caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    merge_story(
        snapshot("app", {"service": {"timeout": 30}}, "app.toml"),
        snapshot("host", {"service": "disabled"}, "host.toml"),
    )
    assert any(record.message == "type_conflict" and record.levelno == logging.WARNING for record in caplog.records)


@os_agnostic
def test_when_mapping_overwrites_scalar_a_warning_is_emitted(caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    merge_story(
        snapshot("app", {"service": "enabled"}, "app.toml"),
        snapshot("host", {"service": {"timeout": 30}}, "host.toml"),
    )
    assert any(record.message == "type_conflict" and record.levelno == logging.WARNING for record in caplog.records)


# --- provenance names exactly what the merged data holds ----------------------------------------
#
# An entry exists for every value and every table that stayed empty, and for nothing else: a
# table with content carries no entry of its own (its values do). An empty table declared in one
# layer and filled by a later one kept the empty declaration's entry, and so did a value a later
# layer replaced by a table; a table replaced by a value kept the entries of the values it held.


@os_agnostic
def test_a_table_declared_empty_and_filled_later_has_no_entry_of_its_own() -> None:
    result = merge_story(
        snapshot("defaults", {"styles": {}}, "defaults.toml"),
        snapshot("dotenv", {"styles": {"DEBUG": "dim"}}, ".env"),
    )
    assert set(result.provenance) == {"styles.DEBUG"}
    assert result.provenance["styles.DEBUG"]["layer"] == "dotenv"


@os_agnostic
def test_a_value_replaced_by_a_table_leaves_no_entry_for_the_table() -> None:
    result = merge_story(
        snapshot("app", {"service": "enabled"}, "app.toml"),
        snapshot("host", {"service": {"timeout": 30}}, "host.toml"),
    )
    assert set(result.provenance) == {"service.timeout"}


@os_agnostic
def test_a_table_replaced_by_a_value_forgets_the_values_it_held() -> None:
    result = merge_story(
        snapshot("app", {"service": {"timeout": 30, "retries": {"max": 3}}}, "app.toml"),
        snapshot("host", {"service": "disabled"}, "host.toml"),
    )
    assert set(result.provenance) == {"service"}
    assert result.provenance["service"]["layer"] == "host"


@os_agnostic
def test_a_table_that_stays_empty_keeps_the_entry_of_the_last_layer_declaring_it() -> None:
    result = merge_story(
        snapshot("defaults", {"styles": {}}, "defaults.toml"),
        snapshot("user", {"styles": {}}, "user.toml"),
    )
    assert result.provenance["styles"]["layer"] == "user"


_DOTLESS_KEY = st.text(alphabet="abc", min_size=1, max_size=2)
_TRANSITION_VALUE = st.recursive(
    st.integers(min_value=0, max_value=3),
    lambda children: st.dictionaries(_DOTLESS_KEY, children, max_size=3),
    max_leaves=8,
)
_TRANSITION_LAYER = st.dictionaries(_DOTLESS_KEY, _TRANSITION_VALUE, max_size=3)


def _values_and_empty_tables(data: dict[str, object], prefix: str = "") -> set[str]:
    found: set[str] = set()
    for key, value in data.items():
        dotted = prefix + key
        if isinstance(value, dict) and value:
            found |= _values_and_empty_tables(value, dotted + ".")
        else:
            found.add(dotted)
    return found


@os_agnostic
@given(st.lists(_TRANSITION_LAYER, min_size=1, max_size=4))
def test_provenance_names_exactly_the_values_and_empty_tables_of_the_merged_data(layers) -> None:
    """Keys from a three-letter alphabet make layers collide, so tables, values and empty tables
    replace each other in every order; keys hold no dot, so a dotted path names one place."""
    result = merge_story(*(snapshot(f"layer{index}", layer) for index, layer in enumerate(layers)))
    assert set(result.provenance) == _values_and_empty_tables(result.data)


@os_agnostic
@pytest.mark.parametrize("replacement", [{"name": "x"}, "none"], ids=["table", "value"])
def test_a_list_replaced_wholesale_forgets_the_entries_of_its_overridden_elements(replacement) -> None:
    """An env override by index records an entry per element value (`ports.0.n`); once a later
    layer replaces the whole list, that element is gone and so must be its entry."""
    result = merge_story(
        snapshot("app", {"ports": [{"n": 1}]}, "app.toml"),
        snapshot("env", {"ports": {"0": {"n": 2}}}),
        snapshot("host", {"ports": replacement}, "host.toml"),
    )
    assert "ports.0.n" not in result.provenance
    assert set(result.provenance) == _values_and_empty_tables(result.data)
