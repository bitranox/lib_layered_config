from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.application.merge import LayerSnapshot, merge_layers

from tests.support.os_markers import os_agnostic


SCALAR = st.one_of(st.booleans(), st.integers(), st.text(min_size=1, max_size=5))
VALUE = st.recursive(
    SCALAR,
    lambda children: st.dictionaries(st.text(min_size=1, max_size=5), children, max_size=3),
    max_leaves=10,
)
MAPPING = st.dictionaries(st.text(min_size=1, max_size=5), VALUE, max_size=4)


def layer(name: str, payload: dict[str, object], origin: str | None = None) -> LayerSnapshot:
    return LayerSnapshot(name, payload, origin)


def feature_layers() -> list[LayerSnapshot]:
    return [
        layer("app", {"feature": {"enabled": False}}, "app.toml"),
        layer("user", {"feature": {"enabled": True}}, "user.toml"),
        layer("env", {"feature": {"level": "debug"}}),
    ]


@os_agnostic
def test_merge_layers_lets_latest_scalar_win() -> None:
    merged, _ = merge_layers(feature_layers())
    assert merged["feature"]["enabled"] is True


@os_agnostic
def test_merge_layers_preserves_new_keys_from_env_layer() -> None:
    merged, _ = merge_layers(feature_layers())
    assert merged["feature"]["level"] == "debug"


@os_agnostic
def test_merge_layers_records_provenance_for_scalar_override() -> None:
    _, meta = merge_layers(feature_layers())
    assert meta["feature.enabled"]["layer"] == "user"


@os_agnostic
def test_merge_layers_records_provenance_for_new_key() -> None:
    _, meta = merge_layers(feature_layers())
    assert meta["feature.level"]["layer"] == "env"


def database_layers() -> list[LayerSnapshot]:
    return [
        layer("app", {"db": {"host": "localhost", "port": 5432}}, "app.toml"),
        layer("dotenv", {"db": {"password": "secret"}}, ".env"),
    ]


@os_agnostic
def test_merge_layers_keeps_existing_nested_values() -> None:
    merged, _ = merge_layers(database_layers())
    assert merged["db"]["host"] == "localhost"


@os_agnostic
def test_merge_layers_adds_new_nested_values() -> None:
    merged, _ = merge_layers(database_layers())
    assert merged["db"]["password"] == "secret"


def idempotent_layers() -> list[LayerSnapshot]:
    return [
        layer("app", {"db": {"host": "localhost", "ports": [5432]}}, "app.toml"),
        layer("env", {"db": {"host": "remote"}}),
    ]


@os_agnostic
def test_merge_layers_is_idempotent_for_payload() -> None:
    merged_a, _ = merge_layers(idempotent_layers())
    merged_b, _ = merge_layers(idempotent_layers())
    assert merged_a == merged_b


@os_agnostic
def test_merge_layers_is_idempotent_for_metadata() -> None:
    _, meta_a = merge_layers(idempotent_layers())
    _, meta_b = merge_layers(idempotent_layers())
    assert meta_a == meta_b


@os_agnostic
def test_merge_layers_does_not_share_mutable_inputs() -> None:
    payload = {"numbers": [1, 2]}
    snapshot = layer("env", payload)
    merged, _ = merge_layers([snapshot])
    payload["numbers"].append(3)
    assert merged["numbers"] == [1, 2]


@os_agnostic
@given(MAPPING, MAPPING, MAPPING)
def test_merge_layers_associative_property(lhs, mid, rhs) -> None:
    left, _ = merge_layers([layer("lhs", lhs), layer("mid", mid), layer("rhs", rhs)])
    left_then_right, _ = merge_layers([layer("lhs-mid", left), layer("rhs", rhs)])
    mid_then_right_payload, _ = merge_layers([layer("mid", mid), layer("rhs", rhs)])
    right_then_left, _ = merge_layers([layer("lhs", lhs), layer("mid-rhs", mid_then_right_payload)])
    assert left_then_right == right_then_left


def _contains(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for key, value in expected.items():
            if key not in actual:
                return False
            if not _contains(actual[key], value):
                return False
        return True
    return actual == expected


@os_agnostic
@given(MAPPING, MAPPING)
def test_last_layer_wins_for_non_empty_payloads(lhs, rhs) -> None:
    merged, _ = merge_layers([layer("lhs", lhs), layer("rhs", rhs)])
    expectation = all(
        _contains(merged[key], value) for key, value in rhs.items() if not (isinstance(value, dict) and not value)
    )
    assert expectation is True
