"""deploy_config takes Layer members as targets, and names a refused one by its value.

``Layer`` is a ``(str, Enum)``, so typed callers pass members. An f-string over a member reads
``Layer.ENV`` on Python 3.11 and later, where the refusal must say ``env`` as it does for the string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config.deploy import deploy_config, deploy_config_paths
from lib_layered_config.domain.errors import ValidationError
from lib_layered_config.domain.identifiers import Layer
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.toml"
    path.write_text("[service]\nport = 1\n", encoding="utf-8")
    return path


@os_agnostic
@pytest.mark.parametrize("layer", [Layer.DEFAULTS, Layer.DOTENV, Layer.ENV])
@pytest.mark.parametrize("deploy", [deploy_config, deploy_config_paths], ids=["deploy_config", "deploy_config_paths"])
def test_a_layer_member_deploy_does_not_write_is_refused_by_its_value(
    sandbox: LayeredSandbox, source: Path, deploy: Callable[..., object], layer: Layer
) -> None:
    with pytest.raises(ValidationError) as caught:
        deploy(source, vendor=VENDOR, app=APP, slug=SLUG, targets=[layer])
    assert str(caught.value) == f"Unsupported deployment target: {layer.value}"
    assert not (sandbox.roots["user"] / "config.toml").exists()


@os_agnostic
def test_a_layer_member_deploy_writes_is_deployed(sandbox: LayeredSandbox, source: Path) -> None:
    results = deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=[Layer.USER])
    assert [result.destination for result in results] == [sandbox.roots["user"] / "config.toml"]


@os_agnostic
def test_a_single_layer_member_as_targets_is_refused_with_the_list_that_works(
    sandbox: LayeredSandbox, source: Path
) -> None:
    with pytest.raises(ValidationError) as caught:
        deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=Layer.USER)
    assert str(caught.value) == "targets takes a sequence of layer names, not a single str: write ['user']"
    assert not (sandbox.roots["user"] / "config.toml").exists()
