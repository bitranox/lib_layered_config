from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.application.merge import merge_layers


SCALAR = st.one_of(st.booleans(), st.integers(), st.text(min_size=1, max_size=5))
VALUE = st.recursive(
    SCALAR,
    lambda children: st.dictionaries(st.text(min_size=1, max_size=5), children, max_size=3),
    max_leaves=10,
)
MAPPING = st.dictionaries(st.text(min_size=1, max_size=5), VALUE, max_size=4)


def test_precedence_overwrites() -> None:
    layers = [
        ("app", {"feature": {"enabled": False}}, "app.toml"),
        ("user", {"feature": {"enabled": True}}, "user.toml"),
        ("env", {"feature": {"level": "debug"}}, None),
    ]
    merged, meta = merge_layers(layers)
    assert merged["feature"]["enabled"] is True
    assert merged["feature"]["level"] == "debug"
    assert meta["feature.enabled"]["layer"] == "user"
    assert meta["feature.level"]["layer"] == "env"


def test_nested_merge_retains_previous_keys() -> None:
    layers = [
        ("app", {"db": {"host": "localhost", "port": 5432}}, "app.toml"),
        ("dotenv", {"db": {"password": "secret"}}, ".env"),
    ]
    merged, _ = merge_layers(layers)
    assert merged["db"]["host"] == "localhost"
    assert merged["db"]["password"] == "secret"


def test_merge_is_idempotent() -> None:
    layers = [
        ("app", {"db": {"host": "localhost", "ports": [5432]}}, "app.toml"),
        ("env", {"db": {"host": "remote"}}, None),
    ]
    merged_a, meta_a = merge_layers(layers)
    merged_b, meta_b = merge_layers(layers)
    assert merged_a == merged_b
    assert meta_a == meta_b


@given(MAPPING, MAPPING, MAPPING)
def test_merge_associative(lhs, mid, rhs) -> None:
    left, _ = merge_layers([("lhs", lhs, None), ("mid", mid, None), ("rhs", rhs, None)])
    left_then_right, _ = merge_layers([("lhs-mid", left, None), ("rhs", rhs, None)])
    right_then_left, _ = merge_layers(
        [("lhs", lhs, None), ("mid-rhs", merge_layers([("mid", mid, None), ("rhs", rhs, None)])[0], None)]
    )
    assert left_then_right == right_then_left


def _assert_contains(actual, expected):
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for sub_key, sub_val in expected.items():
            assert sub_key in actual
            _assert_contains(actual[sub_key], sub_val)
    else:
        assert actual == expected


@given(MAPPING, MAPPING)
def test_last_layer_wins(lhs, rhs) -> None:
    merged, _ = merge_layers([("lhs", lhs, None), ("rhs", rhs, None)])
    for key, value in rhs.items():
        if isinstance(value, dict) and not value:
            continue  # empty mappings do not remove previously merged content
        if key not in merged:
            continue
        _assert_contains(merged[key], value)
