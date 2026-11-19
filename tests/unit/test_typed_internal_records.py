"""Internal values with a fixed shape travel as typed records, never as string-keyed dicts or bare tuples.

A string key rebuilt by formatting (``f"{layer.value}_file"``) or a pair read by position is checked by
nothing: a typo or a swap reads a default, or the wrong loader, without any error. A named record makes
each field a checked attribute.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from lib_layered_config import core
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.domain import deploy_permissions
from lib_layered_config.domain.deploy_mode import ModeKind
from lib_layered_config.domain.identifiers import DEPLOY_LAYERS
from lib_layered_config.domain.redaction import NotSensitiveKeys
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


@os_agnostic
def test_each_mode_setting_names_its_layer_and_kind_as_fields() -> None:
    fields = deploy_permissions._MODE_FIELDS  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject

    for name, field in fields.items():
        assert type(field) is deploy_permissions._ModeField  # pyright: ignore[reportPrivateUsage] - the record type is the subject
        assert name == f"{field.layer.value}_{field.kind.value}"
    assert {(field.layer, field.kind) for field in fields.values()} == set(itertools.product(DEPLOY_LAYERS, ModeKind))


@os_agnostic
def test_the_loaders_come_back_as_a_named_pair(tmp_path: Path) -> None:
    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, env={}, platform="linux")

    loaders = core._build_loaders(resolver, not_sensitive=NotSensitiveKeys.NONE, searches_dotenv=False)  # pyright: ignore[reportPrivateUsage] - the wiring helper itself is the subject

    assert type(loaders) is core._Loaders  # pyright: ignore[reportPrivateUsage] - the record type is the subject
    assert isinstance(loaders.dotenv, DefaultDotEnvLoader)
    assert isinstance(loaders.env, DefaultEnvLoader)
