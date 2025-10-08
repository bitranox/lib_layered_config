from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.application.merge import LayerSnapshot, merge_layers

from tests.support.os_markers import os_agnostic


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


def merge_story(*layers: LayerSnapshot) -> tuple[dict[str, object], dict[str, object]]:
    return merge_layers(list(layers))


@os_agnostic
def test_when_user_layer_sings_last_word_the_scalar_agrees() -> None:
    merged, _ = merge_story(
        snapshot("app", {"feature": {"enabled": False}}, "app.toml"),
        snapshot("user", {"feature": {"enabled": True}}, "user.toml"),
    )
    assert merged["feature"]["enabled"] is True


@os_agnostic
def test_when_env_layer_whispers_new_key_the_story_remembers() -> None:
    merged, _ = merge_story(
        snapshot("app", {"feature": {}}, "app.toml"),
        snapshot("env", {"feature": {"level": "debug"}}),
    )
    assert merged["feature"]["level"] == "debug"


@os_agnostic
def test_when_user_layer_overrides_provenance_points_to_user() -> None:
    _, provenance = merge_story(
        snapshot("app", {"feature": {"enabled": False}}, "app.toml"),
        snapshot("user", {"feature": {"enabled": True}}, "user.toml"),
    )
    assert provenance["feature.enabled"]["layer"] == "user"


@os_agnostic
def test_when_env_layer_adds_key_provenance_points_to_env() -> None:
    _, provenance = merge_story(
        snapshot("app", {"feature": {}}, "app.toml"),
        snapshot("env", {"feature": {"level": "debug"}}),
    )
    assert provenance["feature.level"]["layer"] == "env"


@os_agnostic
def test_when_dotenv_supplies_password_the_payload_keeps_it() -> None:
    merged, _ = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("dotenv", {"db": {"password": "secret"}}, ".env"),
    )
    assert merged["db"]["password"] == "secret"


@os_agnostic
def test_when_branch_becomes_empty_provenance_falls_silent() -> None:
    _, provenance = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": {}}}),
    )
    assert provenance == {}


@os_agnostic
def test_when_merging_twice_the_payload_stays_the_same() -> None:
    first, _ = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    second, _ = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    assert first == second


@os_agnostic
def test_when_merging_twice_the_metadata_sings_the_same_tune() -> None:
    _, first = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    _, second = merge_story(
        snapshot("app", {"db": {"host": "localhost"}}, "app.toml"),
        snapshot("env", {"db": {"host": "remote"}}),
    )
    assert first == second


@os_agnostic
def test_when_original_list_changes_the_merged_copy_stays_still() -> None:
    payload = {"numbers": [1, 2]}
    merged, _ = merge_story(snapshot("env", payload))
    payload["numbers"].append(3)
    assert merged["numbers"] == [1, 2]


@os_agnostic
def test_when_original_dict_changes_the_merged_copy_stays_still() -> None:
    payload = {"nested": {"child": "value"}}
    merged, _ = merge_story(snapshot("env", payload))
    payload["nested"]["child"] = "changed"
    assert merged["nested"]["child"] == "value"


@os_agnostic
def test_when_original_set_changes_the_merged_copy_stays_still() -> None:
    payload = {"choices": {1, 2}}
    merged, _ = merge_story(snapshot("env", payload))
    payload["choices"].add(3)
    assert merged["choices"] == {1, 2}


@os_agnostic
def test_when_original_dict_with_nonstring_keys_changes_the_copy_stays_still() -> None:
    payload = {"strange": {1: "value"}}
    merged, _ = merge_story(snapshot("env", payload))
    payload["strange"][1] = "changed"
    assert merged["strange"][1] == "value"


@os_agnostic
def test_when_original_tuple_travels_through_merge_it_returns_intact() -> None:
    payload = {"paths": ("one", "two")}
    merged, _ = merge_story(snapshot("env", payload))
    assert merged["paths"] == ("one", "two")


@os_agnostic
@given(MAPPING, MAPPING, MAPPING)
def test_associativity_holds_like_a_round_song(lhs, mid, rhs) -> None:
    left, _ = merge_story(snapshot("lhs", lhs), snapshot("mid", mid), snapshot("rhs", rhs))
    step_one, _ = merge_story(snapshot("lhs-mid", left), snapshot("rhs", rhs))
    mid_then_right, _ = merge_story(snapshot("mid", mid), snapshot("rhs", rhs))
    step_two, _ = merge_story(snapshot("lhs", lhs), snapshot("mid-rhs", mid_then_right))
    assert step_one == step_two


@os_agnostic
@given(MAPPING, MAPPING)
def test_latest_non_empty_layer_wins_like_a_final_verse(first, second) -> None:
    merged, _ = merge_story(snapshot("first", first), snapshot("second", second))
    chorus = all(
        _nested_contains(merged.get(key), value)
        for key, value in second.items()
        if not (isinstance(value, dict) and not value)
    )
    assert chorus is True
