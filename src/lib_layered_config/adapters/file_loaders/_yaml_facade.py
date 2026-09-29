"""Typed facade for the optional PyYAML module.

PyYAML ships without type stubs recognised by pyright in strict mode, and the module is
imported dynamically (:func:`importlib.import_module`) because it is an optional
dependency. Route every access through :class:`YAMLModule`, a small structural
:class:`~typing.Protocol` describing only the surface this package uses, so the rest of
the codebase never touches an ``Any``-typed module object.

Contents:
    - ``YAMLModule``: Protocol describing ``safe_load`` and ``YAMLError``.
    - ``as_yaml_module``: single, explicit narrowing point from the dynamically
      imported module to :class:`YAMLModule`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

__all__ = ["YAMLModule", "as_yaml_module"]


class YAMLModule(Protocol):
    """The parts of the ``yaml`` package this library relies on.

    Structural typing lets a real PyYAML module and a hand-built test double (a
    ``SimpleNamespace`` exposing the same two attributes) both satisfy this Protocol.
    """

    YAMLError: type[Exception]
    safe_load: Callable[[str], Any]


def as_yaml_module(module: ModuleType) -> YAMLModule:
    """Narrow a dynamically imported module to :class:`YAMLModule`.

    This is the single place the untyped result of :func:`importlib.import_module`
    is cast; every caller downstream works with the typed Protocol instead.

    Args:
        module: The module object returned by ``importlib.import_module("yaml")``.

    Returns:
        The same object, typed as :class:`YAMLModule`.

    Examples:
        >>> from types import SimpleNamespace
        >>> fake = SimpleNamespace(safe_load=lambda text: {"k": text}, YAMLError=Exception)
        >>> as_yaml_module(fake).safe_load("v")
        {'k': 'v'}
    """
    return cast("YAMLModule", module)
