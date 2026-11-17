"""A provenance entry's ``layer`` is stored as text, and the values a snapshot cannot take are named.

``SourceInfo.layer`` is typed ``str``, but a ``Layer`` member (or a caller's own str-valued enum
member) passes that type and used to be stored as the member, so Python 3.11+ printed it as
``Layer.USER``. ``Config`` stores the member's value. ``LayerSnapshot.of`` rebuilds a snapshot from
a layer name read back from provenance, which can also hold ``"override"`` and a caller's own source
such as ``"cli"``; its refusal names both.
"""

from __future__ import annotations

import io
from enum import Enum

import pytest
from rich.console import Console

from lib_layered_config import OVERRIDE_LAYER, Config, display_config
from lib_layered_config.application.merge import LayerSnapshot
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic


class _CallerSource(str, Enum):
    """A consumer's own source names, the shape lsdsk's OverrideLayer has."""

    CLI = "cli"


def _config_with_layer(layer: str) -> Config:
    """A str-valued enum member is a ``str``, so it passes ``SourceInfo``'s type."""
    return Config({"a": 1}, {"a": {"layer": layer, "path": None, "key": "a"}})


@os_agnostic
@pytest.mark.parametrize(("member", "text"), [(Layer.USER, "user"), (_CallerSource.CLI, "cli")])
def test_an_enum_member_given_as_the_layer_is_stored_as_its_value(member: str, text: str) -> None:
    origin = _config_with_layer(member).origin("a")

    assert origin is not None
    assert type(origin["layer"]) is str
    assert origin["layer"] == text


@os_agnostic
def test_display_config_names_a_member_layer_by_its_value() -> None:
    buffer = io.StringIO()

    display_config(_config_with_layer(Layer.USER), console=Console(file=buffer, color_system=None, width=200))

    assert "# layer:user profile:none" in buffer.getvalue()


@os_agnostic
def test_a_plain_text_layer_is_kept_as_given() -> None:
    origin = _config_with_layer("cli").origin("a")

    assert origin == {"layer": "cli", "path": None, "key": "a"}


@os_agnostic
@pytest.mark.parametrize("name", [OVERRIDE_LAYER, "cli"])
def test_layer_snapshot_of_names_override_and_caller_sources_as_values_it_cannot_rebuild(name: str) -> None:
    with pytest.raises(ValueError, match=f"'{name}' is not a valid Layer") as refused:
        LayerSnapshot.of(name, {}, None)

    message = str(refused.value)
    assert "'override'" in message
    assert "'cli'" in message
