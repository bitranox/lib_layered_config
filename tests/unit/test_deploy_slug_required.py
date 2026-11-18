"""The three deploy functions take ``slug`` as a required argument, like ``read_config``.

Until 9.0.0 a forgotten slug fell back to the app name, so the deploy wrote to ``<root>/<App>/``
while every read looked in ``<root>/<slug>/`` (user decision 2026-11-17, "Required in next major").
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config import deploy_config, deploy_config_paths, read_deploy_config
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_DEPLOY_FUNCTIONS = (deploy_config, deploy_config_paths, read_deploy_config)


@os_agnostic
@pytest.mark.parametrize("function", _DEPLOY_FUNCTIONS, ids=lambda f: f.__name__)
def test_slug_has_no_default(function: Callable[..., Any]) -> None:
    parameter = inspect.signature(function).parameters["slug"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


@os_agnostic
@pytest.mark.parametrize("function", _DEPLOY_FUNCTIONS, ids=lambda f: f.__name__)
def test_a_call_without_slug_is_refused_before_anything_is_read(function: Callable[..., Any], tmp_path: Path) -> None:
    source = tmp_path / "config.toml"
    source.write_text("[a]\nb = 1\n", encoding="utf-8")
    arguments: dict[str, Any] = {"vendor": "Acme", "app": "Demo"}
    if function is read_deploy_config:
        arguments["skip"] = ()
    else:
        arguments["targets"] = ["user"]

    with pytest.raises(TypeError, match="slug"):
        function(source, **arguments)
