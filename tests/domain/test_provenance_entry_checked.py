"""``Config`` refuses a provenance entry that is not ``SourceInfo``-shaped where it is built.

An entry missing ``path`` or ``key``, one that is not a mapping, or one whose ``key`` names another
path used to be stored as given and failed (or answered wrong) at a later ``origin()`` call, far from
the code that built it. Each entry must be a mapping with exactly ``layer`` (text), ``path`` (text or
``None``) and ``key`` (its own dotted key); anything else raises ``ValidationError`` naming the entry.
"""

from __future__ import annotations

import copy
import pickle
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

import pytest

from lib_layered_config import Config, ValidationError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from lib_layered_config.domain.config import SourceInfo


class _CallerSource(str, Enum):
    CLI = "cli"


def _build(entry: object, *, dotted: str = "db.host") -> Config:
    """Build a Config whose provenance holds *entry* under *dotted*, as an untyped caller can."""
    meta = cast("dict[str, SourceInfo]", {dotted: entry})
    return Config({"db": {"host": "h"}}, meta)


_REFUSED: list[tuple[str, object, str]] = [
    ("not a mapping", 7, "provenance entry 'db.host' must be a mapping with the keys layer, path and key, got int"),
    (
        "keys missing",
        {"layer": "env"},
        "provenance entry 'db.host' must have exactly the keys layer, path and key, got 'layer'",
    ),
    (
        "a key too many",
        {"layer": "env", "path": None, "key": "db.host", "extra": 1},
        "provenance entry 'db.host' must have exactly the keys layer, path and key, "
        "got 'extra', 'key', 'layer', 'path'",
    ),
    (
        "layer not text",
        {"layer": 3, "path": None, "key": "db.host"},
        "provenance entry 'db.host': layer must be text, got int",
    ),
    (
        "path not text",
        {"layer": "app", "path": 5, "key": "db.host"},
        "provenance entry 'db.host': path must be text or None, got int",
    ),
    (
        "key names another path",
        {"layer": "env", "path": None, "key": "zzz"},
        "provenance entry 'db.host': key must be 'db.host', its own key in the provenance, got 'zzz'",
    ),
    (
        "key not text",
        {"layer": "env", "path": None, "key": 1},
        "provenance entry 'db.host': key must be 'db.host', its own key in the provenance, got 1",
    ),
]


@os_agnostic
@pytest.mark.parametrize(("entry", "message"), [(e, m) for _, e, m in _REFUSED], ids=[i for i, _, _ in _REFUSED])
def test_a_malformed_provenance_entry_is_refused_at_construction(entry: object, message: str) -> None:
    with pytest.raises(ValidationError) as refused:
        _build(entry)

    assert str(refused.value) == message


@os_agnostic
@pytest.mark.parametrize(
    "entry",
    [
        {"layer": "cli", "path": None, "key": "db.host"},
        {"layer": _CallerSource.CLI, "path": None, "key": "db.host"},
        {"layer": "app", "path": "/etc/app.toml", "key": "db.host"},
    ],
    ids=["caller source text", "caller str enum", "file layer"],
)
def test_a_well_formed_entry_is_accepted(entry: dict[str, Any]) -> None:
    origin = _build(entry).origin("db.host")

    assert origin == {**entry, "layer": str(getattr(entry["layer"], "value", entry["layer"]))}


@os_agnostic
def test_a_config_with_checked_provenance_survives_pickle_and_deepcopy() -> None:
    cfg = _build({"layer": _CallerSource.CLI, "path": None, "key": "db.host"})

    restored = pickle.loads(pickle.dumps(cfg))  # noqa: S301 - bytes this test just made from its own Config
    duplicate = copy.deepcopy(cfg)

    assert restored == cfg
    assert duplicate == cfg
    assert restored.origin("db.host") == {"layer": "cli", "path": None, "key": "db.host"}
