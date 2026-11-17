"""``Config.get_redacted`` walks only the key's path, and answers exactly what the full redacted view shows.

Before, every call built the whole ``as_dict(redact=True)`` copy and then followed one path, so one
call on a 40 000-key configuration took 46 ms and asking for each key in turn grew with the square
of the configuration's size. The oracle here is that full view, followed with a masked ancestor
masking everything below it.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Iterator, Mapping
from typing import Any, cast

import pytest

from lib_layered_config import Config
from lib_layered_config.domain.errors import InvalidFormatError
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, NotSensitiveKeys
from tests.support.os_markers import os_agnostic


def _key_paths(mapping: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> Iterator[str]:
    """Every dotted key path reachable through mappings, as ``Config.get`` addresses them."""
    for key, value in mapping.items():
        path = (*prefix, key)
        yield ".".join(path)
        if isinstance(value, Mapping):
            yield from _key_paths(cast("Mapping[str, Any]", value), path)


def _as_the_full_view_shows(config: Config, dotted: str) -> Any:
    current: Any = config.as_dict(redact=True)
    for fragment in dotted.split("."):
        if current == REDACTED_PLACEHOLDER:
            return REDACTED_PLACEHOLDER
        current = current[fragment]
    return current


_VARIED = {
    "db": {"host": "h", "password": "p", "port": 5432, "pool": {"apiKey": "k", "size": 3}},
    "credentials": {"user": "alice", "nested": {"deeper": 1}},
    "services": [{"name": "a", "token": "t"}, ({"secret": "s", "plain": [1, {"jwt": "j"}]},)],
    "performance": {"max_token_bytes": 4096, "tokens": {"limit": 1}},
    "clientSecret": {"inner": "x"},
    "tags": ("x", "y"),
    "empty": {},
}


@os_agnostic
@pytest.mark.parametrize(
    "declared", [NotSensitiveKeys.NONE, NotSensitiveKeys.of(["performance.max_token_bytes", "performance.tokens"])]
)
def test_every_key_path_answers_what_the_full_redacted_view_shows(declared: NotSensitiveKeys) -> None:
    config = Config(_VARIED, {}, declared)

    paths = list(_key_paths(_VARIED))

    assert len(paths) == 20
    for dotted in paths:
        assert config.get_redacted(dotted) == _as_the_full_view_shows(config, dotted), dotted


@os_agnostic
def test_one_call_does_not_build_the_whole_redacted_configuration() -> None:
    def peak_of_one_call(keys: int) -> int:
        data = {f"s{i // 50}": {f"k{j}": j for j in range(i, i + 50)} for i in range(0, keys, 50)}
        config = Config(data, {})
        config.get_redacted("s0.k0")  # warm
        tracemalloc.start()
        try:
            config.get_redacted("s0.k0")
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    few, many = peak_of_one_call(400), peak_of_one_call(40_000)

    # A copy of the whole configuration grows a hundredfold here; a walk along one path does not.
    assert many < few * 2, (few, many)


@os_agnostic
def test_the_returned_value_is_a_copy_the_caller_cannot_change_the_configuration_through() -> None:
    config = Config({"group": {"members": {"a", "b"}, "order": [1, 2]}}, {})

    returned = config.get_redacted("group")
    returned["members"].add("intruder")
    returned["order"].append(3)

    assert config.get("group.members") == {"a", "b"}
    assert config.get("group.order") == [1, 2]


def _nested_list(levels: int) -> object:
    value: object = 1
    for _ in range(levels):
        value = [value]
    return value


def _nested_mapping(levels: int) -> dict[str, Any]:
    value: dict[str, Any] = {"leaf": 1}
    for _ in range(levels):
        value = {"a": value}
    return value


@os_agnostic
def test_a_too_deep_value_elsewhere_does_not_block_another_key() -> None:
    # User decision 2026-11-16 (C-F4): only the key's own path and value are checked.
    config = Config({"deep": _nested_list(301), "db": {"host": "h"}}, {})

    assert config.get_redacted("db.host") == "h"


@os_agnostic
@pytest.mark.parametrize("levels", [299, 300, 301])
def test_the_too_deep_key_itself_is_refused_where_the_full_view_refuses_it(levels: int) -> None:
    config = Config({"deep": _nested_list(levels)}, {})

    try:
        expected: object = _as_the_full_view_shows(config, "deep")
    except InvalidFormatError as exc:
        with pytest.raises(InvalidFormatError) as caught:
            config.get_redacted("deep")
        assert str(caught.value) == str(exc)
    else:
        assert config.get_redacted("deep") == expected


@os_agnostic
def test_a_scalar_at_the_end_of_a_too_deep_path_is_refused_like_the_full_view_refuses_it() -> None:
    config = Config(_nested_mapping(302), {})
    dotted = ".".join(["a"] * 302 + ["leaf"])

    with pytest.raises(InvalidFormatError, match="maximum depth of 300"):
        config.as_dict(redact=True)
    with pytest.raises(InvalidFormatError, match="maximum depth of 300"):
        config.get_redacted(dotted)


@os_agnostic
def test_a_missing_key_returns_the_default() -> None:
    config = Config({"db": {"host": "h"}}, {})

    assert config.get_redacted("db.port", 7) == 7
    assert config.get_redacted("db.host.deeper") is None


def _mutate_every_container(value: Any) -> None:
    """Change every mutable container reachable from *value*: add to each dict, list and set."""
    if isinstance(value, dict):
        for item in list(cast("dict[str, Any]", value).values()):
            _mutate_every_container(item)
        cast("dict[str, Any]", value)["added"] = "by the caller"
    elif isinstance(value, list):
        for item in list(cast("list[Any]", value)):
            _mutate_every_container(item)
        cast("list[Any]", value).append("by the caller")
    elif isinstance(value, set):
        cast("set[Any]", value).add("by the caller")
    elif isinstance(value, tuple):
        for item in cast("tuple[Any, ...]", value):
            _mutate_every_container(item)


@os_agnostic
@pytest.mark.parametrize("key", ["service", "service.hosts", "service.tags", "service.pairs"])
def test_get_redacted_shares_no_container_with_the_configuration(key: str) -> None:
    data = {
        "service": {
            "hosts": [{"name": "a", "ports": [1, 2]}],
            "tags": {"blue", "green"},
            "pairs": ({"left": [1]}, {"right"}),
            "token": "t",
        }
    }
    config = Config(data, {})
    before = config.as_dict()

    _mutate_every_container(config.get_redacted(key))

    assert config.as_dict() == before
