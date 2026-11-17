"""Typed facade for the optional PyYAML module.

PyYAML ships without type stubs recognised by pyright in strict mode, and the module is
imported dynamically (:func:`importlib.import_module`) because it is an optional
dependency. Route every access through :class:`YAMLModule`, a small structural
:class:`~typing.Protocol` describing only the surface this package uses, so the rest of
the codebase never touches an ``Any``-typed module object.

Contents:
    - ``YAMLModule``: Protocol describing ``SafeLoader`` and ``YAMLError``.
    - ``YAMLLoader``: the safe loader's steps the YAML loader runs (compose, construct, dispose).
    - ``YAMLNode`` / ``YAMLMark``: the composed node graph, as far as the key checks read it.
    - ``as_yaml_module``: single, explicit narrowing point from the dynamically
      imported module to :class:`YAMLModule`.
    - ``safe_loader``: the single narrowing point from ``SafeLoader(document)`` to :class:`YAMLLoader`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from types import ModuleType

__all__ = ["YAMLLoader", "YAMLMark", "YAMLModule", "YAMLNode", "as_yaml_module", "safe_loader"]


class YAMLModule(Protocol):
    """The parts of the ``yaml`` package this library relies on.

    Structural typing lets a real PyYAML module and a hand-built test double (a
    ``SimpleNamespace`` exposing the attributes a test needs) both satisfy this Protocol.
    """

    YAMLError: type[Exception]
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


class YAMLLoader(Protocol):
    """A ``SafeLoader`` over one document: ``yaml.safe_load`` is these three steps.

    Composing resolves tags but constructs nothing, so a repeated key is still two entries and an
    alias is one shared node rather than a copy. Constructing rewrites merge-key (``<<``) mappings in
    place, so whatever reads the node graph reads it before :meth:`construct_document`.
    """

    def get_single_node(self) -> YAMLNode | None:
        """Compose the document's node graph; ``None`` for an empty document."""
        ...

    def construct_document(self, node: YAMLNode) -> object:
        """Build the Python value of *node*."""
        ...

    def dispose(self) -> None:
        """Release the loader's state, as ``yaml.safe_load`` does when it finishes."""
        ...


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
        >>> fake = SimpleNamespace(SafeLoader=object, YAMLError=Exception)
        >>> as_yaml_module(fake).YAMLError is Exception
        True
    """
    return cast("YAMLModule", module)


def safe_loader(module: YAMLModule, document: str) -> YAMLLoader:
    """Return the module's pure-Python safe loader over *document*, typed as :class:`YAMLLoader`.

    Examples:
        >>> from types import SimpleNamespace
        >>> class Loader:
        ...     def __init__(self, document: str) -> None:
        ...         self.document = document
        >>> fake = as_yaml_module(SimpleNamespace(SafeLoader=Loader, YAMLError=Exception))
        >>> isinstance(safe_loader(fake, "a: 1"), Loader)
        True
    """
    return cast("YAMLLoader", module.SafeLoader(document))
