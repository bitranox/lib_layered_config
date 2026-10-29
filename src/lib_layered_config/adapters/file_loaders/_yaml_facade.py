"""Typed facade for the optional PyYAML module.

PyYAML ships without type stubs recognised by pyright in strict mode, and the module is
imported dynamically (:func:`importlib.import_module`) because it is an optional
dependency. Route every access through :class:`YAMLModule`, a small structural
:class:`~typing.Protocol` describing only the surface this package uses, so the rest of
the codebase never touches an ``Any``-typed module object.

Contents:
    - ``YAMLModule``: Protocol describing ``safe_load``, ``compose``, ``SafeLoader`` and ``YAMLError``.
    - ``YAMLNode`` / ``YAMLMark``: the composed node graph, as far as the key checks read it.
    - ``as_yaml_module``: single, explicit narrowing point from the dynamically
      imported module to :class:`YAMLModule`.
    - ``compose_document``: the single narrowing point from ``compose``'s result to :class:`YAMLNode`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

__all__ = ["YAMLMark", "YAMLModule", "YAMLNode", "as_yaml_module", "compose_document"]


class YAMLModule(Protocol):
    """The parts of the ``yaml`` package this library relies on.

    Structural typing lets a real PyYAML module and a hand-built test double (a
    ``SimpleNamespace`` exposing the attributes a test needs) both satisfy this Protocol.
    """

    YAMLError: type[Exception]
    safe_load: Callable[[str], Any]
    compose: Callable[..., Any]
    SafeLoader: type[Any]


class YAMLMark(Protocol):
    """Where a node starts in the document, both counted from 0."""

    line: int
    column: int


class YAMLNode(Protocol):
    """One node of a composed document: ``id`` is ``"scalar"``, ``"sequence"`` or ``"mapping"``.

    ``value`` is the scalar's text, the sequence's nodes, or the mapping's ``(key, value)`` node pairs.
    """

    id: str
    tag: str
    value: Any
    start_mark: YAMLMark


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


def compose_document(module: YAMLModule, document: str) -> YAMLNode | None:
    """Return *document*'s node graph, composed with the safe loader; ``None`` for an empty one.

    Composing resolves tags but constructs nothing, so a repeated key is still two entries and an
    alias is one shared node rather than a copy.

    Examples:
        >>> from types import SimpleNamespace
        >>> fake = SimpleNamespace(compose=lambda text, Loader: None, SafeLoader=object)
        >>> compose_document(as_yaml_module(fake), "") is None
        True
    """
    return cast("YAMLNode | None", module.compose(document, Loader=module.SafeLoader))
