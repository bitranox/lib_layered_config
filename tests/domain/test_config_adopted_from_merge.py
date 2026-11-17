"""A ``Config`` the read functions build from the merge is as immutable as one ``Config(...)`` builds.

``read_config`` and the deploy read hand the merge's own data and provenance to the ``Config``
without the public constructor's second deep copy, because the merge already built them fresh and
nothing else holds them. That is safe only while the merge result shares no container with the
layer payloads it was built from, so these tests pin that, and pin that the adopted ``Config``
still copies on every read and survives ``copy.deepcopy`` and ``pickle`` with its declared
not-sensitive paths.
"""

from __future__ import annotations

import copy
import pickle
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import pytest

from lib_layered_config import Config, Layer, NotSensitiveKeys
from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.core import _compose_config  # pyright: ignore[reportPrivateUsage] - the read path's composition
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterator


def _payloads() -> list[dict[str, Any]]:
    return [
        {"db": {"host": "a", "ports": [1, 2], "opts": {"tls": True}}, "tags": ["x", {"y": [3]}], "empty": {}},
        {"db": {"host": "b", "replicas": [{"name": "r1"}]}, "tags": {"0": "z"}, "levels": (1, [2])},
        {"db": {"token": "t0p"}, "flags": {"on", "off"}},
    ]


def _snapshots(payloads: list[dict[str, Any]]) -> list[LayerSnapshot]:
    layers = (Layer.APP, Layer.USER, Layer.ENV)
    return [LayerSnapshot(layer, payload, None) for layer, payload in zip(layers, payloads, strict=True)]


def _adopted(payloads: list[dict[str, Any]], *, declared: NotSensitiveKeys = NotSensitiveKeys.NONE) -> Config:
    result = merge_layers(_snapshots(payloads))
    return _compose_config(result.data, result.provenance, not_sensitive=declared)


def _containers(value: object) -> Iterator[object]:
    """Every mutable container reachable from *value*, itself included."""
    pending = [value]
    while pending:
        node = pending.pop()
        if isinstance(node, Mapping):
            yield node
            pending.extend(cast("Mapping[object, object]", node).values())
        elif isinstance(node, (list, set)):
            yield node
            pending.extend(cast("list[object] | set[object]", node))
        elif isinstance(node, tuple):
            pending.extend(cast("tuple[object, ...]", node))


def _stored(config: Config) -> list[object]:
    """The containers a Config holds: its data and provenance, read through its private fields."""
    held: list[object] = []
    for mapping in (config._data, config._meta):  # pyright: ignore[reportPrivateUsage] - what the Config stores
        held.extend(_containers(mapping))
        held.extend(_containers(dict(mapping)))
    return held


@os_agnostic
def test_the_adopted_config_shares_no_container_with_the_layer_payloads() -> None:
    payloads = _payloads()

    config = _adopted(payloads)

    payload_ids = {id(container) for container in _containers(payloads)}
    assert not payload_ids & {id(container) for container in _stored(config)}


@os_agnostic
def test_changing_the_payloads_or_the_stored_data_reaches_neither_the_other() -> None:
    payloads = _payloads()
    config = _adopted(payloads)
    before = config.as_dict()

    payloads[0]["db"]["opts"]["tls"] = False
    payloads[0]["tags"][1]["y"].append(4)
    payloads[1]["db"]["replicas"][0]["name"] = "evil"

    assert config.as_dict() == before

    stored = cast("dict[str, Any]", config._data._items)  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType] - the stored dict itself
    stored["db"]["ports"].append(99)
    assert _payloads()[0]["db"]["ports"] == payloads[0]["db"]["ports"] == [1, 2]


@os_agnostic
def test_a_write_through_any_read_of_the_adopted_config_does_not_reach_it() -> None:
    config = _adopted(_payloads())

    config["db"]["host"] = "evil"
    config["db"]["ports"].append(9)
    config.get("db.opts")["tls"] = False
    next(iter(config.values()))["host"] = "evil"
    origin = config.origin("db.host")
    assert origin is not None
    origin["layer"] = "evil"

    assert config.get("db.host") == "b"
    assert config.get("db.ports") == [1, 2]
    assert config.get("db.opts.tls") is True
    assert config.origin("db.host") == {"layer": "user", "path": None, "key": "db.host"}


@os_agnostic
@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_the_adopted_config_pickles_and_keeps_its_declared_paths(protocol: int) -> None:
    config = _adopted(_payloads(), declared=NotSensitiveKeys.of(["db.token"]))

    twin = pickle.loads(pickle.dumps(config, protocol=protocol))  # noqa: S301 - bytes this test just made from its own Config

    assert twin == config
    assert twin.origin("db.token") == config.origin("db.token")
    assert twin.as_dict(redact=True)["db"]["token"] == "t0p"


@os_agnostic
def test_the_adopted_config_deep_copies_and_keeps_its_declared_paths() -> None:
    config = _adopted(_payloads(), declared=NotSensitiveKeys.of(["db.token"]))

    duplicate = copy.deepcopy(config)

    assert duplicate == config
    assert duplicate.as_dict(redact=True)["db"]["token"] == "t0p"
    duplicate["db"]["host"] = "evil"
    assert config.get("db.host") == "b"


@os_agnostic
def test_the_adopted_config_equals_the_one_the_public_constructor_builds() -> None:
    result = merge_layers(_snapshots(_payloads()))
    public = Config(copy.deepcopy(result.data), copy.deepcopy(result.provenance))

    assert _compose_config(result.data, result.provenance) == public
