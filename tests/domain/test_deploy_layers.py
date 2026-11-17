"""The layers a deploy writes are named once, in the domain, and every list of them follows it."""

from __future__ import annotations

from lib_layered_config.cli.constants import TARGET_CHOICES
from lib_layered_config.domain.deploy_permissions import DeployPermissions
from lib_layered_config.domain.identifiers import DEPLOY_LAYERS, Layer
from tests.support.os_markers import os_agnostic


@os_agnostic
def test_deploy_writes_the_app_host_and_user_layers_in_that_order() -> None:
    assert DEPLOY_LAYERS == (Layer.APP, Layer.HOST, Layer.USER)


@os_agnostic
def test_the_cli_target_choices_are_the_deploy_layers() -> None:
    assert tuple(layer.value for layer in DEPLOY_LAYERS) == TARGET_CHOICES == ("app", "host", "user")


@os_agnostic
def test_deploy_permissions_holds_one_field_per_deploy_layer() -> None:
    defaults = DeployPermissions.defaults()
    assert [defaults.for_layer(layer) for layer in DEPLOY_LAYERS] == [defaults.app, defaults.host, defaults.user]
