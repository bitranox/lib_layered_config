"""``lib_layered_config.examples`` is a deprecated alias of ``lib_layered_config.deploy`` and ``.generate``.

Consumers still importing the old path keep working until the shim is removed in 9.0.0;
each import of the package warns so they can see the move coming.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING, cast

import pytest

from lib_layered_config import deploy, generate
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import ModuleType

_SHIM_MODULES = (
    "lib_layered_config.examples.deploy",
    "lib_layered_config.examples.generate",
    "lib_layered_config.examples",
)


def _fresh_import(name: str) -> ModuleType:
    for module in _SHIM_MODULES:
        sys.modules.pop(module, None)
    return importlib.import_module(name)


def _exported(module: ModuleType) -> tuple[str, ...]:
    """The module's ``__all__``, refused unless it is a tuple or list of names."""
    names: object = getattr(module, "__all__", None)
    assert isinstance(names, (tuple, list))
    exported: list[str] = []
    for name in cast("Iterable[object]", names):
        assert isinstance(name, str)
        exported.append(name)
    return tuple(exported)


@os_agnostic
@pytest.mark.parametrize("name", _SHIM_MODULES)
def test_importing_the_old_path_warns(name: str) -> None:
    with pytest.warns(DeprecationWarning, match=r"lib_layered_config\.examples is deprecated"):
        _fresh_import(name)


@os_agnostic
@pytest.mark.parametrize(
    ("old", "new"), [("lib_layered_config.examples.deploy", deploy), ("lib_layered_config.examples.generate", generate)]
)
def test_the_old_modules_re_export_the_same_objects(old: str, new: ModuleType) -> None:
    with pytest.warns(DeprecationWarning):
        shim = _fresh_import(old)
    names = _exported(shim)
    assert names == _exported(new)
    assert all(getattr(shim, name) is getattr(new, name) for name in names)


@os_agnostic
def test_the_old_package_re_exports_its_names_from_the_new_modules() -> None:
    with pytest.warns(DeprecationWarning):
        shim = _fresh_import("lib_layered_config.examples")
    for name in _exported(shim):
        source = deploy if hasattr(deploy, name) else generate
        assert getattr(shim, name) is getattr(source, name)
