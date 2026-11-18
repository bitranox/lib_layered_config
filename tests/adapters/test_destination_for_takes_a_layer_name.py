"""``DefaultPathResolver.destination_for`` takes a layer by member or by name, like ``deploy_config``.

``Layer`` is a ``str`` enum, so the names ``"app"``, ``"host"`` and ``"user"`` (any case) name the same
layers ``deploy_config(targets=...)`` and ``deploy_config_paths`` accept. A layer a deploy does not write,
or a name no layer has, is refused with ``ValidationError`` naming it rather than a bare ``KeyError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from lib_layered_config import Layer, ValidationError
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


def _resolver(tmp_path: Path) -> DefaultPathResolver:
    env = {"LIB_LAYERED_CONFIG_ETC": str(tmp_path / "etc"), "XDG_CONFIG_HOME": str(tmp_path / "home")}
    return DefaultPathResolver(
        vendor="Acme", app="ConfigKit", slug="config-kit", platform="linux", hostname="box", env=env
    )


@os_agnostic
@pytest.mark.parametrize(
    ("name", "layer"),
    [("app", Layer.APP), ("host", Layer.HOST), ("user", Layer.USER), ("USER", Layer.USER), ("App", Layer.APP)],
)
def test_a_layer_name_gives_the_same_destination_as_its_member(tmp_path: Path, name: str, layer: Layer) -> None:
    resolver = _resolver(tmp_path)

    # The annotation says Layer; an untyped caller passes the name, which the deploy functions accept.
    assert resolver.destination_for(cast("Layer", name)) == resolver.destination_for(layer)


@os_agnostic
@pytest.mark.parametrize(("value", "named"), [(Layer.ENV, "env"), ("nope", "nope"), ("dotenv", "dotenv")])
def test_a_layer_a_deploy_does_not_write_is_refused_naming_it(tmp_path: Path, value: str, named: str) -> None:
    resolver = _resolver(tmp_path)

    with pytest.raises(ValidationError, match=f"^Unsupported deployment target: {named}$"):
        resolver.destination_for(cast("Layer", value))
