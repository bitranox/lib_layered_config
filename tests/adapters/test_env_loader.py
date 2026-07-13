"""Environment loader adapter tests clarifying namespace coercion.

The scenarios cover prefix naming, nested assignment, and randomised inputs to
prove the adapter continues to match the documented environment rules.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.adapters._nested_keys import assign_nested
from lib_layered_config.adapters.env.default import (
    DefaultEnvLoader,
    default_env_prefix,
    _normalize_prefix,
    _iter_namespace_entries,
    _coerce,
)

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_default_env_prefix_turns_slug_into_uppercase_snake() -> None:
    assert default_env_prefix("lib-layered-config") == "LIB_LAYERED_CONFIG___"


def _sample_payload() -> dict[str, object]:
    environ = {
        "LIB_LAYERED_CONFIG___DB__HOST": "db.example.com",
        "LIB_LAYERED_CONFIG___DB__PORT": "5432",
        "LIB_LAYERED_CONFIG___FEATURE__ENABLED": "true",
        "OTHER": "ignored",
    }
    loader = DefaultEnvLoader(environ=environ)
    return loader.load("LIB_LAYERED_CONFIG")


@os_agnostic
def test_env_loader_preserves_host_strings() -> None:
    data = _sample_payload()
    assert data["db"]["host"] == "db.example.com"


@os_agnostic
def test_env_loader_coerces_numbers_into_ints() -> None:
    data = _sample_payload()
    assert data["db"]["port"] == 5432


@os_agnostic
def test_env_loader_turns_true_into_boolean() -> None:
    data = _sample_payload()
    assert data["feature"]["enabled"] is True


@os_agnostic
def test_assign_nested_overwrites_scalar_raises_value_error() -> None:
    container: dict[str, object] = {"a": "value"}
    with pytest.raises(ValueError):
        assign_nested(container, "A__B", 1, error_cls=ValueError)


SCALAR_VALUES = st.sampled_from(["0", "1", "true", "false", "3.5", "none", "debug"])
NAMESPACE_KEYS = st.sampled_from(["SERVICE__TIMEOUT", "SERVICE__ENDPOINT", "LOGGING__LEVEL"])


@os_agnostic
@given(st.dictionaries(NAMESPACE_KEYS, SCALAR_VALUES, max_size=3))
def test_env_loader_handles_random_namespace(entries) -> None:
    prefix = "DEMO"
    environ = {f"{prefix}___" + key: value for key, value in entries.items()}
    environ["IGNORED"] = "1"
    payload = DefaultEnvLoader(environ=environ).load(prefix)

    def _expect(value: str) -> object:
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered in {"none", "null"}:
            return None
        if lowered.startswith("-") and lowered[1:].isdigit():
            return int(lowered)
        if lowered.isdigit():
            return int(lowered)
        try:
            return float(value)
        except ValueError:
            return value

    def _lookup(root: dict[str, object], key: str) -> object:
        node: object = root
        for fragment in key.lower().split("__"):
            node = node[fragment]  # type: ignore[index]
        return node

    expectation = (
        all(_lookup(payload, key) == _expect(original) for key, original in entries.items())
        and "ignored" not in payload
    )
    assert expectation is True


@os_agnostic
def test_env_loader_respects_explicit_empty_environment() -> None:
    payload = DefaultEnvLoader(environ={}).load("DEMO")
    assert payload == {}


@os_agnostic
def test_normalize_prefix_preserves_existing_suffix() -> None:
    assert _normalize_prefix("DEMO___") == "DEMO___"


@os_agnostic
def test_iter_namespace_entries_ignores_empty_suffix() -> None:
    entries = list(_iter_namespace_entries([("DEMO___", "value")], "DEMO___"))
    assert entries == []


@os_agnostic
def test_coerce_parses_negative_integers() -> None:
    assert _coerce("-7") == -7


@os_agnostic
def test_coerce_parses_json_array() -> None:
    assert _coerce('["replica1", "replica2"]') == ["replica1", "replica2"]


@os_agnostic
def test_coerce_parses_json_array_of_numbers() -> None:
    assert _coerce("[1, 2, 3]") == [1, 2, 3]


@os_agnostic
def test_coerce_parses_json_object() -> None:
    assert _coerce('{"host": "db", "port": 5432}') == {"host": "db", "port": 5432}


@os_agnostic
def test_coerce_keeps_invalid_json_container_as_string() -> None:
    # Bareword list is not valid JSON; the raw string must survive untouched.
    assert _coerce("[a, b]") == "[a, b]"
    assert _coerce("[unclosed") == "[unclosed"


@os_agnostic
def test_coerce_leaves_plain_scalars_untouched() -> None:
    assert _coerce("hello") == "hello"
    assert _coerce("10") == 10
    assert _coerce("true") is True


@os_agnostic
def test_env_loader_parses_json_array_value() -> None:
    environ = {"MYAPP___DATABASE__REPLICAS": '["replica1", "replica2"]'}
    payload = DefaultEnvLoader(environ=environ).load("MYAPP")
    assert payload["database"]["replicas"] == ["replica1", "replica2"]


@os_agnostic
def test_coerce_parses_nested_json_containers() -> None:
    assert _coerce('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]
    assert _coerce('{"tags": ["x", "y"]}') == {"tags": ["x", "y"]}
    assert _coerce("[[1, 2], [3, 4]]") == [[1, 2], [3, 4]]


@os_agnostic
def test_env_loader_parses_nested_json_value() -> None:
    environ = {"MYAPP___SERVICE__ENDPOINTS": '[{"host": "a", "port": 1}, {"host": "b", "port": 2}]'}
    payload = DefaultEnvLoader(environ=environ).load("MYAPP")
    assert payload["service"]["endpoints"] == [{"host": "a", "port": 1}, {"host": "b", "port": 2}]


@os_agnostic
def test_json_decoded_value_is_independent_between_loads() -> None:
    """orjson allocates fresh objects, so mutating one load must not leak into the next."""
    environ = {"MYAPP___ITEMS": '["a", "b"]'}
    first = DefaultEnvLoader(environ=environ).load("MYAPP")
    assert isinstance(first["items"], list)
    first["items"].append("mutated")
    second = DefaultEnvLoader(environ=environ).load("MYAPP")
    assert second["items"] == ["a", "b"]
